$region = "us-east-1"
$profile = "aussie-ecolens"

$vars = @{
    S3_BUCKET = "aussie-ecolens-g62-prod"
    FILES_TABLE = "AussieEcoLens-Files-prod"
    MEDIA_TAGS_TABLE = "AussieEcoLens-MediaTags-prod"
    TAG_SUBS_TABLE = "AussieEcoLens-TagSubscriptions-prod"
    SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:477216322118:AussieEcoLens-Notifications-prod"
    GCP_INFER_URL = "https://aussie-ecolens-ml-1029582539414.us-central1.run.app"
    GCP_INTERNAL_SECRET = "aussie-ecolens-secret-2026"
}

$envString = ($vars.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ","

Write-Host "Updating API Lambda env..." -ForegroundColor Yellow
aws lambda update-function-configuration `
  --function-name AussieEcoLens-API-prod `
  --environment "Variables={$envString}" `
  --region $region `
  --profile $profile

Write-Host ""
Write-Host "Updating Process Lambda env..." -ForegroundColor Yellow
aws lambda update-function-configuration `
  --function-name AussieEcoLens-Process-prod `
  --environment "Variables={$envString}" `
  --region $region `
  --profile $profile

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
