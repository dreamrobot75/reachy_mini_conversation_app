# Reachy Mini - MuJoCo 3D Simulation & Conversation App Launcher
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Reachy Mini - DeskMate Launcher"

Clear-Host
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Reachy Mini - MuJoCo 3D Simulation & Web UI Launcher" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] Launching MuJoCo 3D Simulation Daemon in a new window..." -ForegroundColor Green
Start-Process "uv" -ArgumentList "run reachy-mini-daemon --sim"

Write-Host "[2/3] Waiting for MuJoCo Daemon (http://127.0.0.1:8000) to be ready..." -ForegroundColor Yellow
$daemonReady = $false
$maxAttempts = 30
$attempt = 0

while (-not $daemonReady -and $attempt -lt $maxAttempts) {
    Start-Sleep -Seconds 1
    $attempt++
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/state/full" -TimeoutSec 1 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $daemonReady = $true
        }
    } catch {
        # Keep waiting
    }
    Write-Host "." -NoNewline
}
Write-Host ""

if ($daemonReady) {
    Write-Host "MuJoCo Simulation Daemon is ready and running on port 8000!" -ForegroundColor Green
} else {
    Write-Host "[Warning] Daemon wait timed out; attempting to connect..." -ForegroundColor Yellow
}

Write-Host "[3/3] Opening Web Talk UI (http://localhost:7860/#/)..." -ForegroundColor Green
Start-Process "http://localhost:7860/#/"

Write-Host ""
Write-Host "Starting Conversation App with desk_companion_ko profile..." -ForegroundColor Cyan
$env:REACHY_MINI_HOST = "localhost"
$env:REACHY_MINI_PORT = "8000"
$env:REACHY_MINI_CUSTOM_PROFILE = "desk_companion_ko"
$env:CONVERSATION_BACKEND = "openai"

uv run python -m reachy_mini_conversation_app.main --ui
