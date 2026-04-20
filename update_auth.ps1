# update_auth.ps1
# Refreshes the NotebookLM session in GCP Secret Manager.
# Run this whenever the session expires (usually after several weeks on Cloud Run).
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - notebooklm CLI installed:  pip install notebooklm-py playwright
#
# Usage:
#   .\update_auth.ps1 -Project YOUR_PROJECT_ID

param(
    [Parameter(Mandatory=$true)]
    [string]$Project,

    [string]$SecretId = "notebooklm-auth",
    [string]$Region   = "us-central1"
)

$ErrorActionPreference = "Stop"
$StorageState = "$env:USERPROFILE\.notebooklm\storage_state.json"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  NotebookLM Auth Refresh" -ForegroundColor Cyan
Write-Host "  Project : $Project" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Log in to NotebookLM
Write-Host "[1/2] Opening browser for Google login..." -ForegroundColor Yellow
Write-Host "      A browser window will open. Log in to Google and close it when done." -ForegroundColor White
notebooklm login

if (-not (Test-Path $StorageState)) {
    Write-Error "Login failed - session file not found at: $StorageState"
}

# Verify valid JSON
try {
    $content = [System.IO.File]::ReadAllText($StorageState, [System.Text.Encoding]::UTF8)
    $null = $content | ConvertFrom-Json
    Write-Host "  Session file is valid." -ForegroundColor Green
} catch {
    Write-Error "Session file is not valid JSON: $_"
}

# Step 2: Upload to Secret Manager (raw bytes - avoids BOM)
Write-Host "[2/2] Uploading session to Secret Manager secret '$SecretId'..." -ForegroundColor Yellow
gcloud config set project $Project

$bytes = [System.IO.File]::ReadAllBytes($StorageState)
$tmpFile = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllBytes($tmpFile, $bytes)
gcloud secrets versions add $SecretId --data-file=$tmpFile
Remove-Item $tmpFile -Force

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Auth updated successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "  Verify with a test run:" -ForegroundColor White
Write-Host "  gcloud run jobs execute psychiatry-weekly-review --region=$Region --wait" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Green
