# Deploys Ring Breaker to Cloud Run (asia-southeast1). Run from the repo root after `gcloud auth login`.
# Usage: .\deploy.ps1 -Project <your-gcp-project-id>
param([Parameter(Mandatory = $true)][string]$Project, [string]$Region = "asia-southeast1")
$ErrorActionPreference = "Stop"

function Set-Secret([string]$Name, [string]$Value) {
  # write without a trailing newline (a newline would corrupt keys)
  $tmp = New-TemporaryFile
  [IO.File]::WriteAllText($tmp, $Value)
  $has = gcloud secrets list --filter="name~$Name" --format="value(name)"
  if (-not $has) { gcloud secrets create $Name --data-file=$tmp } else { gcloud secrets versions add $Name --data-file=$tmp }
  Remove-Item $tmp
}

gcloud config set project $Project
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com `
  aiplatform.googleapis.com secretmanager.googleapis.com firestore.googleapis.com generativelanguage.googleapis.com

# Firestore (native mode) for officer decisions; ignore the error if it already exists.
$ErrorActionPreference = "Continue"
gcloud firestore databases create --location=$Region --type=firestore-native
$ErrorActionPreference = "Stop"

# Consortium masking key in Secret Manager (created once, random).
$exists = gcloud secrets list --filter="name~rb-consortium-key" --format="value(name)"
if (-not $exists) {
  $bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  Set-Secret "rb-consortium-key" ([BitConverter]::ToString($bytes) -replace "-", "")
}

# Runtime service account may call Vertex AI (Gemini) and read the secret.
$num = gcloud projects describe $Project --format="value(projectNumber)"
$sa = "$num-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding $Project --member="serviceAccount:$sa" --role="roles/aiplatform.user" --condition=None | Out-Null
gcloud secrets add-iam-policy-binding rb-consortium-key --member="serviceAccount:$sa" --role="roles/secretmanager.secretAccessor" | Out-Null
gcloud projects add-iam-policy-binding $Project --member="serviceAccount:$sa" --role="roles/datastore.user" --condition=None | Out-Null

# Gemma (bank-side assistant) is reached through the Gemini API, so the service also gets an API key.
# Put a key from Google AI Studio (same project) in $env:GOOGLE_API_KEY before running this script.
$secrets = "RB_CONSORTIUM_KEY=rb-consortium-key:latest"
if ($env:GOOGLE_API_KEY) {
  Set-Secret "rb-gemini-api-key" $env:GOOGLE_API_KEY
  gcloud secrets add-iam-policy-binding rb-gemini-api-key --member="serviceAccount:$sa" --role="roles/secretmanager.secretAccessor" | Out-Null
  $secrets = "$secrets,GOOGLE_API_KEY=rb-gemini-api-key:latest"
  $llmEnv = "GOOGLE_GENAI_USE_VERTEXAI=false"
} else {
  # No key: everything runs on Vertex AI with the service account (Gemma falls back to Gemini Flash-Lite).
  $llmEnv = "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$Project,GOOGLE_CLOUD_LOCATION=global"
}

gcloud run deploy ring-breaker --source . --region $Region --allow-unauthenticated `
  --min-instances 1 --max-instances 3 --memory 2Gi --cpu 2 --timeout 300 `
  --set-env-vars "$llmEnv,RB_STORE=firestore" `
  --set-secrets $secrets

gcloud run services describe ring-breaker --region $Region --format="value(status.url)"
