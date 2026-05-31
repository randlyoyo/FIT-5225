gcloud run deploy aussie-ecolens-ml `
  --image=gcr.io/fit-5225-a2/aussie-ecolens-ml `
  --platform=managed `
  --region=us-central1 `
  --project=fit-5225-a2 `
  --memory=2Gi `
  --cpu=2 `
  --min-instances=1 `
  --max-instances=3 `
  --timeout=300 `
  --set-env-vars "COGNITO_USER_POOL_ID=us-east-1_X2Cb0Asro" `
  --set-env-vars "COGNITO_REGION=us-east-1" `
  --set-env-vars "INTERNAL_API_SECRET=aussie-ecolens-secret-2026" `
  --set-env-vars "AWS_API_BASE_URL=https://bgxu6v2h6f.execute-api.us-east-1.amazonaws.com/prod" `
  --set-env-vars "DEV_MODE=true" `
  --allow-unauthenticated

if ($LASTEXITCODE -eq 0) {
    Write-Host "Done!" -ForegroundColor Green
}
