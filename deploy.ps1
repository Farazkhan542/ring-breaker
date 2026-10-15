# Deploys Ring Breaker to Cloud Run (asia-southeast1). Run from the repo root after `gcloud auth login`.
# Usage: .\deploy.ps1 -Project <your-gcp-project-id>
param([Parameter(Mandatory = $true)][string]$Project, [string]$Region = "asia-southeast1")
$ErrorActionPreference = "Stop"

gcloud config set project $Project
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com `
  aiplatform.googleapis.com secretmanager.googleapis.com

# Consortium masking key in Secret Manager (created once, random).
$exists = gcloud secrets list --filter="name~rb-consortium-key" --format="value(name)"
if (-not $exists) {
  $key = -join ((48..57) + (97..102) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
  $key | gcloud secrets create rb-consortium-key --data-file=-
}

# Runtime service account may call Vertex AI (Gemini) and read the secret.
$num = gcloud projects describe $Project --format="value(projectNumber)"
$sa = "$num-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding $Project --member="serviceAccount:$sa" --role="roles/aiplatform.user" --condition=None | Out-Null
gcloud secrets add-iam-policy-binding rb-consortium-key --member="serviceAccount:$sa" --role="roles/secretmanager.secretAccessor" | Out-Null

gcloud run deploy ring-breaker --source . --region $Region --allow-unauthenticated `
  --min-instances 1 --max-instances 3 --memory 2Gi --cpu 2 --timeout 300 `
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$Project,GOOGLE_CLOUD_LOCATION=global" `
  --set-secrets "RB_CONSORTIUM_KEY=rb-consortium-key:latest"

gcloud run services describe ring-breaker --region $Region --format="value(status.url)"
