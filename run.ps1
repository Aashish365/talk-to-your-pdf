#Requires -Version 5.1
<#
.SYNOPSIS
    Talk-to-your-PDF -- one-shot setup and launch for Windows PowerShell.
    Ollama is expected to be running locally on port 11434.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step { param($m) Write-Host "`n---- $m ----" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "[OK]    $m"    -ForegroundColor Green }
function Write-Warn { param($m) Write-Host "[WARN]  $m"    -ForegroundColor Yellow }
function Write-Fail { param($m) Write-Host "[ERROR] $m"    -ForegroundColor Red; exit 1 }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ---- 1. Docker ------------------------------------------------------------------
Write-Step 'Checking Docker'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail 'Docker not found. Install Docker Desktop: https://docs.docker.com/desktop/windows/install/'
}

docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Fail 'Docker daemon is not running. Open Docker Desktop and wait for it to start, then re-run.'
}

$dockerVer = (docker --version) -replace 'Docker version ','' -replace ',.*',''
Write-Ok "Docker $dockerVer"

# ---- 2. Docker Compose ----------------------------------------------------------
Write-Step 'Checking Docker Compose'

$composeCmd = $null
docker compose version 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    $composeCmd = 'docker compose'
} elseif (Get-Command docker-compose -ErrorAction SilentlyContinue) {
    $composeCmd = 'docker-compose'
} else {
    Write-Fail 'Docker Compose not found. Update Docker Desktop or install the Compose plugin.'
}

$composeVer = Invoke-Expression "$composeCmd version --short 2>&1"
Write-Ok "Compose: $composeVer"

# ---- 3. Local Ollama check -------------------------------------------------------
Write-Step 'Checking local Ollama'

try {
    $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 5 -ErrorAction Stop
    $models = $tags.models | ForEach-Object { $_.name }
    Write-Ok "Ollama is running. Models: $($models -join ', ')"
} catch {
    Write-Fail 'Ollama is not reachable at http://localhost:11434. Make sure Ollama is running locally.'
}

# ---- 4. Ports -------------------------------------------------------------------
Write-Step 'Checking required ports'

$ports = @{ 3000 = 'frontend'; 8000 = 'backend'; 6333 = 'qdrant'; 6379 = 'redis' }
foreach ($port in $ports.Keys) {
    $inUse = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($inUse) {
        Write-Warn "Port $port ($($ports[$port])) is already in use"
    } else {
        Write-Ok "Port $port ($($ports[$port])) is free"
    }
}

# ---- 5. Disk space --------------------------------------------------------------
Write-Step 'Checking disk space'

$drive  = (Get-Item $ScriptDir).PSDrive.Name
$disk   = Get-PSDrive $drive
$freeGB = [math]::Round($disk.Free / 1GB, 1)
if ($freeGB -lt 5) {
    Write-Warn "Only ${freeGB}GB free. Consider freeing space before uploading large PDFs."
} else {
    Write-Ok "${freeGB}GB available"
}

# ---- 6. Environment file --------------------------------------------------------
Write-Step 'Checking environment file'

$envFile     = Join-Path $ScriptDir '.env'
$envExample  = Join-Path $ScriptDir '.env.example'

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Ok '.env created from .env.example — edit it if you need custom settings'
    } else {
        Write-Fail '.env.example not found. Cannot create .env automatically.'
    }
} else {
    Write-Ok '.env already exists'
}

# ---- 7. Data directory ----------------------------------------------------------
Write-Step 'Preparing data directory'

New-Item -ItemType Directory -Force -Path (Join-Path $ScriptDir 'data\sessions') | Out-Null
Write-Ok 'data\sessions ready'

# ---- 8. Build and start services ------------------------------------------------
Write-Step 'Building and starting services (may take a few minutes on first run)'

Invoke-Expression "$composeCmd up -d --build"
if ($LASTEXITCODE -ne 0) { Write-Fail 'docker compose up failed. Check the output above.' }
Write-Ok 'All containers started'

# ---- 8. Wait for backend health -------------------------------------------------
Write-Step 'Waiting for backend to be healthy'

$maxWait = 60
$waited  = 0
$healthy = $false
while ($waited -lt $maxWait) {
    try {
        Invoke-RestMethod -Uri 'http://localhost:8000/health' -TimeoutSec 3 -ErrorAction Stop | Out-Null
        $healthy = $true
        break
    } catch {}
    Write-Host "  waiting for backend... ($waited s)" -NoNewline
    Write-Host "`r" -NoNewline
    Start-Sleep 2
    $waited += 2
}
Write-Host ""
if ($healthy) {
    Write-Ok 'Backend is healthy'
} else {
    Write-Warn 'Backend health check timed out -- it may still be starting'
}

# ---- 9. Open browser ------------------------------------------------------------
Write-Step 'Opening browser'

Start-Process 'http://localhost:3000'
Write-Ok 'Opened frontend at http://localhost:3000'

# ---- 10. Stream backend logs in a new window ------------------------------------
Write-Step 'Opening backend log window'

$logCmd = "Set-Location '$ScriptDir'; Write-Host 'Backend logs (Ctrl+C to close)' -ForegroundColor Cyan; docker compose logs -f backend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $logCmd
Write-Ok 'Backend logs streaming in new window'

# ---- 11. Done -------------------------------------------------------------------
Write-Host ""
Write-Host "+------------------------------------------------+" -ForegroundColor Green
Write-Host "|   Talk to your PDF is ready!                  |" -ForegroundColor Green
Write-Host "+------------------------------------------------+" -ForegroundColor Green
Write-Host "|  App        ->  http://localhost:3000         |" -ForegroundColor Green
Write-Host "|  API docs   ->  http://localhost:8000/docs    |" -ForegroundColor Green
Write-Host "|  API raw    ->  http://localhost:8000         |" -ForegroundColor Green
Write-Host "|  Qdrant     ->  http://localhost:6333         |" -ForegroundColor Green
Write-Host "+------------------------------------------------+" -ForegroundColor Green
Write-Host "|  Logs:   docker compose logs -f               |" -ForegroundColor Green
Write-Host "|  Stop:   docker compose down                  |" -ForegroundColor Green
Write-Host "+------------------------------------------------+" -ForegroundColor Green
