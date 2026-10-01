#requires -Version 5.1
$ErrorActionPreference = "Stop"

$Remote = "zethcine-r2"
$Bucket = "cinesphere-videos"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Pause-Screen {
    Write-Host ""
    Read-Host "Pressione ENTER para continuar"
}

function Require-Rclone {
    if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
        Write-Host "ERRO: rclone não foi encontrado no PATH." -ForegroundColor Red
        exit 1
    }
}

function Get-Folders {
    @(Get-ChildItem -LiteralPath $ScriptRoot -Directory |
      Where-Object { $_.Name -notin @(".git","node_modules") } |
      Sort-Object Name)
}

function Choose-Folder {
    param([string]$Title)
    $folders = @(Get-Folders)
    Write-Host ""
    Write-Host $Title -ForegroundColor Cyan
    if ($folders.Count -eq 0) {
        Write-Host "Nenhuma pasta encontrada no mesmo diretório do script." -ForegroundColor Yellow
        return $null
    }
    for ($i=0; $i -lt $folders.Count; $i++) {
        Write-Host ("{0} - {1}" -f ($i+1),$folders[$i].Name)
    }
    do {
        $n=0
        $ok=[int]::TryParse((Read-Host "Escolha o número da pasta"),[ref]$n) -and $n -ge 1 -and $n -le $folders.Count
        if (-not $ok) { Write-Host "Escolha inválida." -ForegroundColor Yellow }
    } until ($ok)
    return $folders[$n-1]
}

function Validate-Qualities {
    param([string]$Path)
    $missing=@()
    foreach($q in @("1080","720","480","320")) {
        $p=Join-Path $Path $q
        if(-not(Test-Path -LiteralPath $p -PathType Container)) { $missing += $q; continue }
        if(@(Get-ChildItem -LiteralPath $p -File -Recurse).Count -eq 0) { $missing += "$q (vazia)" }
    }
    if($missing.Count -gt 0) {
        Write-Host "Estrutura incompleta: $($missing -join ', ')" -ForegroundColor Yellow
        return ((Read-Host "Continuar mesmo assim? (S/N)") -match "^[sS]")
    }
    return $true
}

function Upload-Folder {
    param([string]$LocalPath,[string]$Destination)
    $files=@(Get-ChildItem -LiteralPath $LocalPath -File -Recurse)
    $bytes=($files | Measure-Object Length -Sum).Sum
    if($null -eq $bytes){$bytes=0}
    Write-Host ""
    Write-Host "Origem: $LocalPath"
    Write-Host "Destino: $Destination"
    Write-Host ("Arquivos: {0} | Tamanho: {1:N2} GB" -f $files.Count,($bytes/1GB))
    if((Read-Host "Confirmar upload? (S/N)") -notmatch "^[sS]"){ Write-Host "Cancelado."; return }

    & rclone copy $LocalPath $Destination `
        --progress --stats=10s --stats-one-line `
        --transfers=8 --checkers=16 `
        --retries=10 --low-level-retries=20 --retries-sleep=5s --fast-list

    if($LASTEXITCODE -ne 0) {
        Write-Host "ERRO: rclone terminou com código $LASTEXITCODE." -ForegroundColor Red
        return
    }

    Write-Host "Upload concluído." -ForegroundColor Green
    Write-Host "Verificando tamanho/objetos remotos..." -ForegroundColor Cyan
    & rclone size $Destination
    Write-Host ""
    Write-Host "Listagem remota:" -ForegroundColor Cyan
    & rclone lsf $Destination --recursive
}

function Upload-Filme {
    $folder=Choose-Folder "PASTAS DE FILMES DISPONÍVEIS"
    if($null -eq $folder){return}
    if(-not(Validate-Qualities $folder.FullName)){return}
    Upload-Folder $folder.FullName "${Remote}:${Bucket}/$($folder.Name)"
}

function Upload-Serie {
    Write-Host ""
    Write-Host "UPLOAD DE SÉRIE" -ForegroundColor Cyan
    $seriesName=(Read-Host "Nome da série no R2").Trim()
    if([string]::IsNullOrWhiteSpace($seriesName)){Write-Host "Nome inválido.";return}

    $episodes=@(Get-Folders)
    if($episodes.Count -eq 0){Write-Host "Nenhuma pasta de episódio encontrada.";return}

    Write-Host ""
    for($i=0;$i -lt $episodes.Count;$i++){Write-Host ("{0} - {1}" -f ($i+1),$episodes[$i].Name)}
    Write-Host "0 - Enviar todos os episódios"

    do {
        $n=0
        $ok=[int]::TryParse((Read-Host "Escolha"),[ref]$n) -and $n -ge 0 -and $n -le $episodes.Count
        if(-not $ok){Write-Host "Escolha inválida." -ForegroundColor Yellow}
    } until($ok)

    if($n -eq 0) {
        foreach($ep in $episodes) {
            if(Validate-Qualities $ep.FullName) {
                Upload-Folder $ep.FullName "${Remote}:${Bucket}/$seriesName/$($ep.Name)"
            }
        }
    } else {
        $ep=$episodes[$n-1]
        if(Validate-Qualities $ep.FullName) {
            Upload-Folder $ep.FullName "${Remote}:${Bucket}/$seriesName/$($ep.Name)"
        }
    }
}

Require-Rclone

while($true) {
    Clear-Host
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "       ZETHCINE R2 UPLOADER" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Bucket: $Bucket"
    Write-Host "Pasta do script: $ScriptRoot"
    Write-Host ""
    Write-Host "1 - Enviar FILME"
    Write-Host "2 - Enviar SÉRIE"
    Write-Host "3 - Listar bucket"
    Write-Host "0 - Sair"
    Write-Host ""
    switch(Read-Host "Escolha") {
        "1" { Upload-Filme; Pause-Screen }
        "2" { Upload-Serie; Pause-Screen }
        "3" { & rclone lsf "${Remote}:${Bucket}" --recursive; Pause-Screen }
        "0" { exit 0 }
        default { Write-Host "Opção inválida." -ForegroundColor Yellow; Start-Sleep 1 }
    }
}
