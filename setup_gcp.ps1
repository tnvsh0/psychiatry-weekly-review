# ── setup_gcp.ps1 ─────────────────────────────────────────────────────────────
# One-time setup: creates all GCP resources for the psychiatry weekly review job.
# Run this ONCE from your PC after cloning the repo.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated:  gcloud auth login
#   - gh CLI installed and authenticated:      gh auth login
#   - You are logged in to NotebookLM:         notebooklm login
#
# Usage:
#   .\setup_gcp.ps1 -Project YOUR_PROJECT_ID -GhRepo tnvsh0/psychiatry-weekly-review
# ──────────────────────────────────────────────────────────────────────────────

param(
    [Parameter(Mandatory=$true)]
    [string]$Project,

    [string]$GhRepo    = "tnvsh0/psychiatry-weekly-review",
    [string]$Region    = "us-central1",
    [string]$JobName   = "psychiatry-weekly-review",
    [string]$ImageName = "psychiatry-weekly-review",
    [string]$SecretId  = "notebooklm-auth",
    [string]$NtfyTopic = ""   # optional — set if you use ntfy push notifications
)

$ErrorActionPreference = "Stop"
$Registry = "$Region-docker.pkg.dev/$Project/psychiatry/$ImageName"

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Psychiatry Weekly Review — GCP Setup" -ForegroundColor Cyan
Write-Host "  Project : $Project" -ForegroundColor Cyan
Write-Host "  Region  : $Region" -ForegroundColor Cyan
Write-Host "  Image   : $Registry" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── 1. Set active project ──────────────────────────────────────────────────────
Write-Host "[1/9] Setting active project..." -ForegroundColor Yellow
gcloud config set project $Project

# ── 2. Enable required APIs ────────────────────────────────────────────────────
Write-Host "[2/9] Enabling APIs (Run, Artifact Registry, Secret Manager, Scheduler)..." -ForegroundColor Yellow
gcloud services enable `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    secretmanager.googleapis.com `
    cloudscheduler.googleapis.com `
    cloudbuild.googleapis.com

# ── 3. Create Artifact Registry repository ────────────────────────────────────
Write-Host "[3/9] Creating Artifact Registry repository 'psychiatry'..." -ForegroundColor Yellow
$repoExists = gcloud artifacts repositories describe psychiatry --location=$Region --format="value(name)" 2>$null
if (-not $repoExists) {
    gcloud artifacts repositories create psychiatry `
        --repository-format=docker `
        --location=$Region `
        --description="Psychiatry weekly review Docker images"
    Write-Host "  Repository created." -ForegroundColor Green
} else {
    Write-Host "  Repository already exists, skipping." -ForegroundColor Gray
}

# ── 4. Build & push Docker image ──────────────────────────────────────────────
Write-Host "[4/9] Building and pushing Docker image..." -ForegroundColor Yellow
gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet
docker build -t "${Registry}:latest" .
docker push "${Registry}:latest"
Write-Host "  Image pushed: ${Registry}:latest" -ForegroundColor Green

# ── 5. Create Secret Manager secret for NotebookLM auth ──────────────────────
Write-Host "[5/9] Uploading NotebookLM session to Secret Manager..." -ForegroundColor Yellow
$StorageState = "$env:USERPROFILE\.notebooklm\storage_state.json"
if (-not (Test-Path $StorageState)) {
    Write-Error "NotebookLM session not found at $StorageState. Run: notebooklm login"
}

$secretExists = gcloud secrets describe $SecretId --format="value(name)" 2>$null
if (-not $secretExists) {
    gcloud secrets create $SecretId --replication-policy=automatic
}
# Use stdin to avoid BOM / encoding issues
Get-Content $StorageState -Raw | `
    [System.Text.Encoding]::UTF8.GetBytes($_) | `
    gcloud secrets versions add $SecretId --data-file=-
Write-Host "  Secret '$SecretId' updated." -ForegroundColor Green

# ── 6. Create service account ─────────────────────────────────────────────────
Write-Host "[6/9] Creating service account..." -ForegroundColor Yellow
$SA = "weekly-review-runner@$Project.iam.gserviceaccount.com"
$saExists = gcloud iam service-accounts describe $SA --format="value(email)" 2>$null
if (-not $saExists) {
    gcloud iam service-accounts create weekly-review-runner `
        --display-name="Weekly Review Runner"
    Write-Host "  Service account created." -ForegroundColor Green
} else {
    Write-Host "  Service account already exists, skipping." -ForegroundColor Gray
}

# Grant access to the secret
gcloud secrets add-iam-policy-binding $SecretId `
    --member="serviceAccount:$SA" `
    --role="roles/secretmanager.secretAccessor"

# ── 7. Create Cloud Run Job ────────────────────────────────────────────────────
Write-Host "[7/9] Creating Cloud Run Job '$JobName'..." -ForegroundColor Yellow

$EnvVars = "NOTEBOOKLM_AUTH_JSON=projects/$Project/secrets/$SecretId/versions/latest"
if ($NtfyTopic) {
    $EnvVars += ",NTFY_TOPIC=$NtfyTopic"
}
# GitHub token needed for Release uploads
$EnvVars += ",GH_REPO=$GhRepo"

$jobExists = gcloud run jobs describe $JobName --region=$Region --format="value(name)" 2>$null
if (-not $jobExists) {
    gcloud run jobs create $JobName `
        --image="${Registry}:latest" `
        --region=$Region `
        --service-account=$SA `
        --set-secrets="NOTEBOOKLM_AUTH_JSON=${SecretId}:latest" `
        --set-env-vars="GH_REPO=$GhRepo$(if($NtfyTopic){",NTFY_TOPIC=$NtfyTopic"})" `
        --memory=2Gi `
        --cpu=2 `
        --max-retries=1 `
        --task-timeout=7200s
    Write-Host "  Job created." -ForegroundColor Green
} else {
    gcloud run jobs update $JobName `
        --image="${Registry}:latest" `
        --region=$Region `
        --service-account=$SA `
        --set-secrets="NOTEBOOKLM_AUTH_JSON=${SecretId}:latest" `
        --set-env-vars="GH_REPO=$GhRepo$(if($NtfyTopic){",NTFY_TOPIC=$NtfyTopic"})" `
        --memory=2Gi `
        --cpu=2 `
        --max-retries=1 `
        --task-timeout=7200s
    Write-Host "  Job updated." -ForegroundColor Green
}

# ── 8. Create Cloud Scheduler trigger (Sunday 06:00 UTC) ─────────────────────
Write-Host "[8/9] Creating Cloud Scheduler job (Sunday 06:00 UTC)..." -ForegroundColor Yellow
$JobUri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$Project/jobs/$JobName`:run"

$schedulerExists = gcloud scheduler jobs describe "$JobName-trigger" --location=$Region --format="value(name)" 2>$null
if (-not $schedulerExists) {
    gcloud scheduler jobs create http "$JobName-trigger" `
        --location=$Region `
        --schedule="0 6 * * 0" `
        --uri=$JobUri `
        --http-method=POST `
        --oauth-service-account-email=$SA `
        --time-zone="UTC" `
        --description="Weekly psychiatry literature review — every Sunday 06:00 UTC"
    Write-Host "  Scheduler job created." -ForegroundColor Green
} else {
    Write-Host "  Scheduler job already exists, skipping." -ForegroundColor Gray
}

# ── 9. Save config for CI/CD ──────────────────────────────────────────────────
Write-Host "[9/9] Setting GitHub Actions secrets for CI/CD..." -ForegroundColor Yellow
# Create a Workload Identity service account key for GitHub Actions
# (simpler alternative: use a JSON key — fine for personal projects)
$KeyFile = "$env:TEMP\weekly-review-sa-key.json"
gcloud iam service-accounts keys create $KeyFile --iam-account=$SA
$KeyJson = [System.IO.File]::ReadAllText($KeyFile, [System.Text.Encoding]::UTF8)
gh secret set GCP_SA_KEY --body $KeyJson --repo $GhRepo
gh secret set GCP_PROJECT --body $Project --repo $GhRepo
gh secret set GCP_REGION --body $Region --repo $GhRepo
Remove-Item $KeyFile -Force
Write-Host "  GitHub secrets set: GCP_SA_KEY, GCP_PROJECT, GCP_REGION" -ForegroundColor Green

# Also set NTFY_TOPIC if provided
if ($NtfyTopic) {
    gh secret set NTFY_TOPIC --body $NtfyTopic --repo $GhRepo
    Write-Host "  GitHub secret set: NTFY_TOPIC" -ForegroundColor Green
}

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Green
Write-Host "  1. Push code to GitHub — CI/CD will auto-deploy on every push to main." -ForegroundColor White
Write-Host "  2. Test manually:" -ForegroundColor White
Write-Host "     gcloud run jobs execute $JobName --region=$Region --wait" -ForegroundColor Cyan
Write-Host "  3. Check logs:" -ForegroundColor White
Write-Host "     gcloud run jobs executions list --job=$JobName --region=$Region" -ForegroundColor Cyan
Write-Host "  4. When auth expires, run:  .\update_auth.ps1 -Project $Project" -ForegroundColor White
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Green
