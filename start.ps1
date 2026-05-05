# Usage: .\start.ps1
# Starts Ollama, pulls required models, verifies spaCy models,
# then launches the backend (FastAPI :8000) and frontend (React :3000).

$BACKEND_URL  = "http://localhost:8000"
$FRONTEND_URL = "http://localhost:3000"

function Write-Step { param($msg) Write-Host "[*] $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "[ERR] $msg" -ForegroundColor Red }

# Load .env into the current process environment
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' } | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
        }
    }
}

# Resolve values from env with fallbacks
$OLLAMA_URL  = if ($env:OLLAMA_HOST)  { $env:OLLAMA_HOST }  else { "http://localhost:11434" }
$LLM_MODELS  = if ($env:LLM_MODELS)  { $env:LLM_MODELS  -split ',' | ForEach-Object { $_.Trim() } } else { @("sciphi/triplex") }
$SPACY_MODELS = if ($env:SPACY_MODELS) { $env:SPACY_MODELS -split ',' | ForEach-Object { $_.Trim() } } else { @("en_core_web_trf") }

# Check if a URL responds with HTTP 200
function Test-Http {
    param($url)
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

# [1/5] Ollama daemon
Write-Step "[1/5] Checking Ollama..."
if (-not (Test-Http "$OLLAMA_URL/api/tags")) {
    Write-Warn "Ollama not running — starting ollama serve"
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    if (-not (Test-Http "$OLLAMA_URL/api/tags")) {
        Write-Err "Ollama failed to start. Is it installed?"
        exit 1
    }
}
Write-Ok "Ollama is running"

# [2/5] Ollama LLM models
Write-Step "[2/5] Checking Ollama LLM models..."
try {
    $tagsJson    = Invoke-RestMethod -Uri "$OLLAMA_URL/api/tags" -TimeoutSec 5
    $pulledNames = $tagsJson.models | ForEach-Object { $_.name -replace ":latest$", "" }
} catch {
    $pulledNames = @()
}

foreach ($model in $LLM_MODELS) {
    $shortName = $model -replace ":latest$", ""
    if ($pulledNames -contains $shortName) {
        Write-Ok "LLM model present: $model"
    } else {
        Write-Warn "Pulling LLM model: $model"
        & ollama pull $model
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to pull $model"
            exit 1
        }
        Write-Ok "Pulled: $model"
    }
}

# [3/5] spaCy NLP models
Write-Step "[3/5] Checking spaCy models..."
foreach ($model in $SPACY_MODELS) {
    $result = & python -c "import spacy; spacy.load('$model'); print('ok')" 2>&1
    if ("$result" -match "ok") {
        Write-Ok "spaCy model present: $model"
    } else {
        Write-Warn "spaCy model not found: $model — downloading..."
        & python -m spacy download $model
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to download spaCy model: $model"
            exit 1
        }
        Write-Ok "Downloaded spaCy model: $model"
    }
}

# [4/5] Backend
Write-Step "[4/5] Starting backend (uvicorn on :8000)..."
$backendJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location $root
    & "$root\venv\Scripts\Activate.ps1"
    & "$root\venv\Scripts\uvicorn.exe" backend.main:app --host 0.0.0.0 --port 8000
} -ArgumentList $PWD.Path

Start-Sleep -Seconds 5
if (Test-Http "$BACKEND_URL/health") {
    Write-Ok "Backend healthy at $BACKEND_URL"
} else {
    Write-Warn "Backend did not respond in time — check logs below"
}

# [5/5] Frontend
Write-Step "[5/5] Starting frontend (npm start on :3000)..."
$frontendJob = Start-Job -ScriptBlock {
    param($root)
    Set-Location "$root\frontend"
    & npm start
} -ArgumentList $PWD.Path

# Summary
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Backend   $BACKEND_URL"              -ForegroundColor Green
Write-Host "  Frontend  $FRONTEND_URL"             -ForegroundColor Green
Write-Host "  Ollama    $OLLAMA_URL"               -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop all services"   -ForegroundColor Yellow
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Stream job output until Ctrl+C
try {
    while ($true) {
        Receive-Job -Job $backendJob  | ForEach-Object { Write-Host "[backend]  $_" }
        Receive-Job -Job $frontendJob | ForEach-Object { Write-Host "[frontend] $_" }
        Start-Sleep -Milliseconds 500

        if ($backendJob.State -eq "Failed") {
            Write-Err "Backend job failed"
            break
        }
        if ($frontendJob.State -eq "Failed") {
            Write-Err "Frontend job failed"
            break
        }
    }
} finally {
    Write-Host ""
    Write-Step "Shutting down..."
    Stop-Job  -Job $backendJob,  $frontendJob -ErrorAction SilentlyContinue
    Remove-Job -Job $backendJob, $frontendJob -ErrorAction SilentlyContinue -Force
    Write-Ok "All services stopped"
}
