#requires -Version 5.1
<#
.SYNOPSIS
  Upload e verificação recursiva da biblioteca ZethCine no Cloudflare R2.

  Estrutura esperada:

  FILMES\
    filme-001\
      1080\
      720\
      480\
      320\

  SERIES\
    serie-001\
      ep-01\
        1080\
        720\
        480\
        320\

  O script usa rclone copy, não sync.
  Portanto, não apaga arquivos existentes no R2.

  Antes de considerar um upload concluído, executa:
    - contagem/tamanho local
    - upload recursivo
    - contagem/tamanho remoto
    - rclone check
#>

$ErrorActionPreference = "Stop"

$Remote = "zethcine-r2"

# Ajuste somente estas duas linhas se suas pastas estiverem em outro local.
$MoviesRoot = "D:\ZethCine\FILMES"
$SeriesRoot = "D:\ZethCine\SERIES"

function Write-Section($Text) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Pause-Script {
    Write-Host ""
    Read-Host "Pressione ENTER para continuar"
}

function Require-Rclone {
    try {
        Get-Command rclone -ErrorAction Stop | Out-Null
    }
    catch {
        throw "rclone não foi encontrado. Abra um novo PowerShell ou execute o script de configuração primeiro."
    }
}

function Test-SourcePath($Path, $Type) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Pasta raiz de $Type não encontrada: $Path"
    }
}

function Get-LocalStats($Path) {
    $files = @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction Stop)
    $bytes = ($files | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $bytes) { $bytes = 0 }

    [PSCustomObject]@{
        Files = $files.Count
        Bytes = [int64]$bytes
        Size = ("{0:N2} GB" -f ($bytes / 1GB))
    }
}

function Get-RcloneStats($RemotePath) {
    $json = & rclone size $RemotePath --json 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Não foi possível consultar o destino: $RemotePath`n$($json -join "`n")"
    }

    try {
        return ($json -join "`n") | ConvertFrom-Json
    }
    catch {
        throw "Resposta inesperada do rclone size: $($json -join "`n")"
    }
}

function Validate-ContentStructure($Path, $Type) {
    Write-Host ""
    Write-Host "Validando estrutura de $Type..." -ForegroundColor Yellow

    $children = @(Get-ChildItem -LiteralPath $Path -Directory -Force)

    if ($children.Count -eq 0) {
        throw "Nenhuma pasta de conteúdo encontrada em $Path"
    }

    $expectedQualities = @("1080", "720", "480", "320")
    $problems = New-Object System.Collections.Generic.List[string]

    if ($Type -eq "FILMES") {
        foreach ($item in $children) {
            $qualityDirs = @(Get-ChildItem -LiteralPath $item.FullName -Directory -Force |
                Where-Object { $_.Name -in $expectedQualities } |
                Select-Object -ExpandProperty Name)

            foreach ($quality in $expectedQualities) {
                if ($qualityDirs -notcontains $quality) {
                    $problems.Add("$($item.Name): qualidade $quality ausente")
                }
            }
        }
    }
    else {
        foreach ($series in $children) {
            $episodes = @(Get-ChildItem -LiteralPath $series.FullName -Directory -Force)

            if ($episodes.Count -eq 0) {
                $problems.Add("$($series.Name): nenhum episódio encontrado")
                continue
            }

            foreach ($episode in $episodes) {
                $qualityDirs = @(Get-ChildItem -LiteralPath $episode.FullName -Directory -Force |
                    Where-Object { $_.Name -in $expectedQualities } |
                    Select-Object -ExpandProperty Name)

                foreach ($quality in $expectedQualities) {
                    if ($qualityDirs -notcontains $quality) {
                        $problems.Add("$($series.Name)\$($episode.Name): qualidade $quality ausente")
                    }
                }
            }
        }
    }

    if ($problems.Count -gt 0) {
        Write-Host ""
        Write-Host "ATENÇÃO: foram encontradas inconsistências:" -ForegroundColor Yellow
        $problems | Select-Object -First 50 | ForEach-Object {
            Write-Host " - $_" -ForegroundColor Yellow
        }

        if ($problems.Count -gt 50) {
            Write-Host " - ... e mais $($problems.Count - 50) problema(s)." -ForegroundColor Yellow
        }

        $answer = Read-Host "Deseja continuar mesmo assim? (S/N)"
        if ($answer -notmatch '^(S|s|SIM|sim)$') {
            throw "Upload cancelado devido a inconsistências na estrutura."
        }
    }
    else {
        Write-Host "Estrutura de qualidades: OK" -ForegroundColor Green
    }
}

function Upload-And-Verify($SourcePath, $RemotePath, $TypeName) {
    Write-Section "UPLOAD: $TypeName"

    Write-Host "Origem:  $SourcePath"
    Write-Host "Destino: $RemotePath"

    Validate-ContentStructure $SourcePath $TypeName

    Write-Host ""
    Write-Host "Calculando tamanho e quantidade de arquivos locais..." -ForegroundColor Yellow
    $local = Get-LocalStats $SourcePath

    Write-Host ""
    Write-Host "LOCAL" -ForegroundColor Cyan
    Write-Host "Arquivos: $($local.Files)"
    Write-Host "Tamanho:  $($local.Size)"

    Write-Host ""
    Write-Host "Iniciando upload recursivo..." -ForegroundColor Yellow
    Write-Host "A estrutura de diretórios será preservada."
    Write-Host ""

    & rclone copy $SourcePath $RemotePath `
        --progress `
        --stats=10s `
        --stats-one-line `
        --transfers=8 `
        --checkers=16 `
        --retries=10 `
        --low-level-retries=20 `
        --retries-sleep=5s `
        --fast-list

    if ($LASTEXITCODE -ne 0) {
        throw "O rclone terminou com código $LASTEXITCODE. O upload NÃO deve ser considerado concluído."
    }

    Write-Host ""
    Write-Host "Upload terminou. Iniciando conferência..." -ForegroundColor Yellow

    $remote = Get-RcloneStats $RemotePath

    Write-Host ""
    Write-Host "COMPARAÇÃO DE CONTAGEM/TAMANHO" -ForegroundColor Cyan
    Write-Host "Local : $($local.Files) arquivos / $($local.Size)"
    Write-Host "R2    : $($remote.count) arquivos / $("{0:N2} GB" -f ($remote.bytes / 1GB))"

    if ([int64]$remote.count -ne [int64]$local.Files) {
        Write-Host ""
        Write-Host "ATENÇÃO: quantidade de arquivos diferente." -ForegroundColor Red
    }

    if ([int64]$remote.bytes -ne [int64]$local.Bytes) {
        Write-Host "ATENÇÃO: tamanho total diferente." -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "Executando rclone check..." -ForegroundColor Yellow
    Write-Host "Isso não altera nem a origem nem o R2."
    Write-Host ""

    & rclone check $SourcePath $RemotePath `
        --one-way `
        --size-only `
        --combined=- `
        --missing-on-dst=-

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "A VERIFICAÇÃO ENCONTROU DIFERENÇAS." -ForegroundColor Red
        Write-Host "NÃO considere este conteúdo totalmente validado."
        return $false
    }

    Write-Host ""
    Write-Host "✓ UPLOAD E VERIFICAÇÃO CONCLUÍDOS." -ForegroundColor Green
    Write-Host "✓ Estrutura preservada."
    Write-Host "✓ Nenhuma diferença detectada pelo check."

    return $true
}

function Show-Menu {
    Write-Section "ZETHCINE R2 UPLOADER"

    Write-Host "Remote configurado: $Remote" -ForegroundColor Green
    Write-Host ""
    Write-Host "1 - Enviar filme"
    Write-Host "2 - Enviar série"
    Write-Host "3 - Verificar filme"
    Write-Host "4 - Verificar série"
    Write-Host "5 - Enviar + verificar filme"
    Write-Host "6 - Enviar + verificar série"
    Write-Host "0 - Sair"
    Write-Host ""
}

function Select-Directory($Root, $Label) {
    Test-SourcePath $Root $Label

    $items = @(Get-ChildItem -LiteralPath $Root -Directory -Force | Sort-Object Name)

    if ($items.Count -eq 0) {
        throw "Nenhum item encontrado em $Root"
    }

    Write-Host ""
    Write-Host "$Label disponíveis:" -ForegroundColor Yellow

    for ($i = 0; $i -lt $items.Count; $i++) {
        Write-Host ("[{0}] {1}" -f ($i + 1), $items[$i].Name)
    }

    Write-Host ""
    $choice = Read-Host "Digite o número"

    $number = 0
    if (-not [int]::TryParse($choice, [ref]$number)) {
        throw "Escolha inválida."
    }

    if ($number -lt 1 -or $number -gt $items.Count) {
        throw "Escolha fora da lista."
    }

    return $items[$number - 1]
}

function Do-Verify($SourcePath, $RemotePath, $Label) {
    Write-Section "VERIFICAÇÃO: $Label"

    $local = Get-LocalStats $SourcePath
    $remote = Get-RcloneStats $RemotePath

    Write-Host "Local: $($local.Files) arquivos / $($local.Size)"
    Write-Host "R2   : $($remote.count) arquivos / $("{0:N2} GB" -f ($remote.bytes / 1GB))"

    Write-Host ""
    Write-Host "Executando rclone check..." -ForegroundColor Yellow

    & rclone check $SourcePath $RemotePath --one-way

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✓ VERIFICAÇÃO OK: nenhum arquivo diferente ou ausente." -ForegroundColor Green
        return
    }

    Write-Host ""
    Write-Host "✗ FORAM ENCONTRADAS DIFERENÇAS." -ForegroundColor Red
}

try {
    Require-Rclone

    Write-Section "INICIALIZAÇÃO"

    $remoteList = @(rclone listremotes)
    if ($remoteList -notcontains "$Remote`:") {
        Write-Host "O remote '$Remote' não existe." -ForegroundColor Red
        Write-Host "Execute primeiro: .\configurar-zethcine-rclone.ps1"
        exit 1
    }

    while ($true) {
        Show-Menu
        $option = Read-Host "Escolha"

        try {
            switch ($option) {
                "1" {
                    $item = Select-Directory $MoviesRoot "FILMES"
                    $source = $item.FullName
                    $destination = "$Remote`:filmes/$($item.Name)"
                    Upload-And-Verify $source $destination "FILME $($item.Name)"
                    Pause-Script
                }

                "2" {
                    $item = Select-Directory $SeriesRoot "SERIES"
                    $source = $item.FullName
                    $destination = "$Remote`:series/$($item.Name)"
                    Upload-And-Verify $source $destination "SÉRIE $($item.Name)"
                    Pause-Script
                }

                "3" {
                    $item = Select-Directory $MoviesRoot "FILMES"
                    $source = $item.FullName
                    $destination = "$Remote`:filmes/$($item.Name)"
                    Do-Verify $source $destination "FILME $($item.Name)"
                    Pause-Script
                }

                "4" {
                    $item = Select-Directory $SeriesRoot "SERIES"
                    $source = $item.FullName
                    $destination = "$Remote`:series/$($item.Name)"
                    Do-Verify $source $destination "SÉRIE $($item.Name)"
                    Pause-Script
                }

                "5" {
                    $item = Select-Directory $MoviesRoot "FILMES"
                    $source = $item.FullName
                    $destination = "$Remote`:filmes/$($item.Name)"
                    $ok = Upload-And-Verify $source $destination "FILME $($item.Name)"
                    Pause-Script
                }

                "6" {
                    $item = Select-Directory $SeriesRoot "SERIES"
                    $source = $item.FullName
                    $destination = "$Remote`:series/$($item.Name)"
                    $ok = Upload-And-Verify $source $destination "SÉRIE $($item.Name)"
                    Pause-Script
                }

                "0" {
                    Write-Host "Encerrando."
                    exit 0
                }

                default {
                    Write-Host "Opção inválida." -ForegroundColor Yellow
                }
            }
        }
        catch {
            Write-Host ""
            Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
            Pause-Script
        }
    }
}
catch {
    Write-Host ""
    Write-Host "ERRO FATAL: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
