# Deploys Ring Breaker to Cloud Run (asia-southeast1). Run from the repo root after `gcloud auth login`.
# Usage: .\deploy.ps1 -Project <project-id> [-BillingAccount <XXXXXX-XXXXXX-XXXXXX>] [-BudgetUsd 30]
# Gemini runs on Vertex AI (billed to the project). Gemma is reached through the Gemini API: put a Google AI Studio
# key in $env:GOOGLE_API_KEY before running and it is stored in Secret Manager as rb-gemma-api-key.
param([Parameter(Mandatory = $true)][string]$Project, [string]$Region = "asia-southeast1",
      [string]$BillingAccount = "", [int]$BudgetUsd = 30)
$ErrorActionPreference = "Stop"

function Set-Secret([string]$Name, [string]$Value) {
  # write without a trailing newline (a newline would corrupt keys)
  $tmp = New-TemporaryFile
  [IO.File]::WriteAllText($tmp, $Value)
  $has = gcloud secrets list --project $Project --filter="name~$Name" --format="value(name)"
  if (-not $has) { gcloud secrets create $Name --project $Project --data-file=$tmp }
  else { gcloud secrets versions add $Name --project $Project --data-file=$tmp }
  Remove-Item $tmp
}

gcloud config set project $Project

# Billing: link the account if given, and stop early if billing is still off.
if ($BillingAccount) { gcloud billing projects link $Project --billing-account=$BillingAccount }
$enabled = gcloud billing projects describe $Project --format="value(billingEnabled)"
if ("$enabled".Trim() -ne "True") { throw "Billing is not enabled on $Project yet." }
$ba = (gcloud billing projects describe $Project --format="value(billingAccountName)") -replace "billingAccounts/", ""

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com `
  aiplatform.googleapis.com secretmanager.googleapis.com firestore.googleapis.com generativelanguage.googleapis.com `
  billingbudgets.googleapis.com

# Firestore (native mode) for officer decisions; an "already exists" error is fine.
$ErrorActionPreference = "Continue"
gcloud firestore databases create --location=$Region --type=firestore-native --project $Project
# Budget alert on the billing account (emails at 50%, 90% and 100%).
$hasBudget = gcloud billing budgets list --billing-account=$ba --filter="displayName=Ring Breaker" --format="value(name)"
if (-not $hasBudget) {
  gcloud billing budgets create --billing-account=$ba --display-name="Ring Breaker" --budget-amount="$($BudgetUsd)USD" `
    --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
}
$ErrorActionPreference = "Stop"

# Consortium masking key in Secret Manager (created once, random).
$exists = gcloud secrets list --project $Project --filter="name~rb-consortium-key" --format="value(name)"
if (-not $exists) {
  $bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  Set-Secret "rb-consortium-key" ([BitConverter]::ToString($bytes) -replace "-", "")
}

# Runtime and build service account: Vertex AI, Firestore, secrets, and building from source.
$num = gcloud projects describe $Project --format="value(projectNumber)"
$sa = "$num-compute@developer.gserviceaccount.com"
foreach ($role in "roles/aiplatform.user", "roles/datastore.user", "roles/run.builder") {
  gcloud projects add-iam-policy-binding $Project --member="serviceAccount:$sa" --role=$role --condition=None | Out-Null
}
gcloud secrets add-iam-policy-binding rb-consortium-key --project $Project --member="serviceAccount:$sa" `
  --role="roles/secretmanager.secretAccessor" | Out-Null

$secrets = "RB_CONSORTIUM_KEY=rb-consortium-key:latest"
if ($env:GOOGLE_API_KEY) {
  Set-Secret "rb-gemma-api-key" $env:GOOGLE_API_KEY
  gcloud secrets add-iam-policy-binding rb-gemma-api-key --project $Project --member="serviceAccount:$sa" `
    --role="roles/secretmanager.secretAccessor" | Out-Null
  $secrets = "$secrets,RB_GEMMA_API_KEY=rb-gemma-api-key:latest"
} else {
  Write-Warning "No GOOGLE_API_KEY set: the bank assistant will use Gemini Flash-Lite instead of Gemma."
}

gcloud run deploy ring-breaker --source . --region $Region --project $Project --allow-unauthenticated --quiet `
  --min-instances 1 --max-instances 3 --cpu 1 --memory 1Gi --timeout 300 `
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$Project,GOOGLE_CLOUD_LOCATION=global,RB_STORE=firestore" `
  --set-secrets $secrets

gcloud run services describe ring-breaker --region $Region --project $Project --format="value(status.url)"
