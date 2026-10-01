#requires -Version 5.1
<#
.SYNOPSIS
  Configura automaticamente o rclone para Cloudflare R2 do ZethCine.

.NOTES
  Execute em um PowerShell novo depois de instalar o rclone:
    winget install Rclone.Rclone

  O script não grava as credenciais em texto neste arquivo.
  O rclone armazena a configuração no arquivo próprio dele.
#>

$ErrorActionPreference = "Stop"

function Write-Section($Text) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
}

function Read-Secret($Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

Write-Section "ZETHCINE - CONFIGURADOR RCLONE + CLOUDFLARE R2"

try {
    $rclone = Get-Command rclone -ErrorAction Stop
}
catch {
    Write-Host "ERRO: rclone não foi encontrado neste PowerShell." -ForegroundColor Red
    Write-Host "Feche esta janela, abra um novo PowerShell e tente novamente."
    Write-Host "Se ainda falhar, execute: where.exe rclone"
    exit 1
}

Write-Host "rclone encontrado: $($rclone.Source)" -ForegroundColor Green
& rclone version | Select-Object -First 1

Write-Section "DADOS DO CLOUDFLARE R2"

$accountId = Read-Host "Cloudflare Account ID"
$accountId = $accountId.Trim()

if ([string]::IsNullOrWhiteSpace($accountId)) {
    throw "Account ID não informado."
}

$accessKey = Read-Host "R2 Access Key ID"
$accessKey = $accessKey.Trim()

if ([string]::IsNullOrWhiteSpace($accessKey)) {
    throw "Access Key ID não informado."
}

$secretKey = Read-Secret "R2 Secret Access Key"
if ([string]::IsNullOrWhiteSpace($secretKey)) {
    throw "Secret Access Key não informado."
}

$remote = "zethcine-r2"
$endpoint = "https://$accountId.r2.cloudflarestorage.com"

Write-Section "CRIANDO REMOTE"

# Remove somente o remote com o mesmo nome, se já existir.
& rclone config delete $remote 2>$null

# Usa o próprio rclone para criar a configuração.
# O bloco é passado via stdin para evitar colocar o segredo em argumentos da linha de comando.
$configText = @"
[$remote]
type = s3
provider = Cloudflare
access_key_id = $accessKey
secret_access_key = $secretKey
region = auto
endpoint = $endpoint
acl = private
"@

$tempConfig = Join-Path $env:TEMP "zethcine-rclone-config-$([guid]::NewGuid().ToString('N')).ini"
$configText | Set-Content -LiteralPath $tempConfig -Encoding UTF8

try {
    # Importa a configuração para o arquivo do rclone.
    $rcloneConfigPath = (& rclone config file | Select-Object -Last 1).Trim()

    if ([string]::IsNullOrWhiteSpace($rcloneConfigPath)) {
        throw "Não foi possível descobrir o arquivo de configuração do rclone."
    }

    if ($rcloneConfigPath -match '^\s*Configuration file is stored at:\s*(.+)$') {
        $rcloneConfigPath = $Matches[1].Trim()
    }

    if (-not (Test-Path $rcloneConfigPath)) {
        # Algumas versões retornam somente o caminho; criar a pasta se necessário.
        $parent = Split-Path -Parent $rcloneConfigPath
        if ($parent -and -not (Test-Path $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
    }

    # Faz backup da configuração existente.
    if (Test-Path $rcloneConfigPath) {
        $backup = "$rcloneConfigPath.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item $rcloneConfigPath $backup -Force
        Write-Host "Backup criado: $backup" -ForegroundColor Yellow
    }

    # Usa a API de configuração do rclone via arquivo temporário.
    # Se já existir config, preserva os demais remotes.
    $existing = ""
    if (Test-Path $rcloneConfigPath) {
        $existing = Get-Content -LiteralPath $rcloneConfigPath -Raw
    }

    # Remove um bloco [zethcine-r2] antigo, se houver.
    if ($existing) {
        $pattern = '(?ms)^\[' + [regex]::Escape($remote) + '\]\s*.*?(?=^\[|\z)'
        $existing = [regex]::Replace($existing, $pattern, '')
        $existing = $existing.Trim()
    }

    if ($existing) {
        $newContent = $existing + "`r`n`r`n" + $configText.Trim() + "`r`n"
    }
    else {
        $newContent = $configText
    }

    Set-Content -LiteralPath $rcloneConfigPath -Value $newContent -Encoding UTF8

    Write-Host "Remote '$remote' configurado." -ForegroundColor Green
}
finally {
    Remove-Item $tempConfig -Force -ErrorAction SilentlyContinue
}

Write-Section "TESTANDO R2"

try {
    $buckets = @(rclone lsd "${remote}:" 2>&1)
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host ($buckets -join "`n") -ForegroundColor Red
        throw "Não foi possível acessar o R2. Confira Account ID e credenciais."
    }

    Write-Host "Conexão com R2: OK" -ForegroundColor Green

    if ($buckets.Count -gt 0) {
        Write-Host ""
        Write-Host "Buckets encontrados:" -ForegroundColor Yellow
        $buckets | ForEach-Object { Write-Host $_ }
    }
    else {
        Write-Host "Nenhum bucket foi listado." -ForegroundColor Yellow
    }
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

Write-Section "SELECIONAR BUCKET"

$bucket = Read-Host "Nome EXATO do bucket do ZethCine"
$bucket = $bucket.Trim()

if ([string]::IsNullOrWhiteSpace($bucket)) {
    throw "Bucket não informado."
}

try {
    & rclone lsf "$remote`:$bucket" --max-depth 1 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Bucket '$bucket' não pôde ser acessado."
    }
}
catch {
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Section "CONFIGURAÇÃO CONCLUÍDA"

Write-Host "Remote:  $remote" -ForegroundColor Green
Write-Host "Bucket:  $bucket" -ForegroundColor Green
Write-Host "Endpoint: $endpoint" -ForegroundColor Green

Write-Host ""
Write-Host "Teste final:" -ForegroundColor Yellow
& rclone lsf "$remote`:$bucket" --max-depth 2

Write-Host ""
Write-Host "O próximo passo é usar o arquivo zethcine-upload.ps1."
Write-Host "Exemplo:"
Write-Host "  .\zethcine-upload.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "NÃO compartilhe seu rclone.conf, pois ele contém as credenciais do R2." -ForegroundColor Yellow
