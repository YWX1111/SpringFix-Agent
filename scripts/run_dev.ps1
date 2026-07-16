# SpringFix Agent dev launcher (Windows PowerShell)
# Usage:
#   .\scripts\run_dev.ps1
# Prerequisites:
#   uv sync

$ErrorActionPreference = "Stop"

Write-Host "[run_dev] Starting SpringFix Agent (M0)..." -ForegroundColor Cyan

# Ensure dependencies are synced
uv sync --extra dev
if ($LASTEXITCODE -ne 0) {
    Write-Host "[run_dev] uv sync failed" -ForegroundColor Red
    exit 1
}

# Load HOST/PORT from .env if present, fallback to defaults
$host_ = "0.0.0.0"
$port = 8000
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^HOST=(.+)$") { $host_ = $matches[1].Trim() }
        if ($_ -match "^PORT=(.+)$") { $port = [int]$matches[1].Trim() }
    }
}

Write-Host "[run_dev] Listening on http://${host_}:${port}" -ForegroundColor Cyan
Write-Host "[run_dev] Health: http://localhost:${port}/api/v1/health" -ForegroundColor Cyan
Write-Host "[run_dev] Docs:    http://localhost:${port}/docs" -ForegroundColor Cyan

uv run uvicorn springfix_agent.main:app --host $host_ --port $port --reload
