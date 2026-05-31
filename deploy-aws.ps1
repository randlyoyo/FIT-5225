# AussieEcoLens AWS Deployment Script
# Run: .\deploy-aws.ps1

$env:PYTHONUTF8 = 1
[System.Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$stackName = "AussieEcoLens"
$bucket    = "aussie-ecolens-deploy-g62"
$profile   = "aussie-ecolens"
$region    = "us-east-1"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Deploying AussieEcoLens to AWS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# === Step 1: Deploy CloudFormation ===
Write-Host "[1/3] Deploying CloudFormation stack..." -ForegroundColor Yellow

aws cloudformation deploy `
  --template-file infra/cloudformation.yaml `
  --stack-name $stackName `
  --parameter-overrides "Environment=prod" "GCPInferUrl=https://placeholder-infer-url.a.run.app" "GCPInternalSecret=aussie-ecolens-secret-2026" "LambdaDeployBucket=$bucket" `
  --capabilities CAPABILITY_IAM `
  --profile $profile `
  --region $region

if ($LASTEXITCODE -ne 0) {
    Write-Host "Deployment failed. Check error above." -ForegroundColor Red
    exit 1
}

Write-Host "Stack created." -ForegroundColor Green
Write-Host ""

# === Step 2: Set up S3 notification ===
Write-Host "[2/3] Configuring S3 event trigger..." -ForegroundColor Yellow

$lambdaArn = aws cloudformation describe-stacks `
  --stack-name $stackName `
  --profile $profile `
  --region $region `
  --query "Stacks[0].Outputs[?OutputKey=='ProcessLambdaArn'].OutputValue" `
  --output text

if ($lambdaArn) {
    $s3bucket = "aussie-ecolens-g62-prod"
    aws s3api put-bucket-notification-configuration `
      --bucket $s3bucket `
      --notification-configuration "{\"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"$lambdaArn\",\"Events\":[\"s3:ObjectCreated:*\"],\"Filter\":{\"Key\":{\"FilterRules\":[{\"Name\":\"prefix\",\"Value\":\"originals/\"}]}}}]}" `
      --profile $profile `
      --region $region
    Write-Host "S3 notification configured." -ForegroundColor Green
} else {
    Write-Host "WARNING: Could not find ProcessLambdaArn. Run this manually later." -ForegroundColor Yellow
}
Write-Host ""

# === Step 3: Show outputs ===
Write-Host "[3/3] Stack outputs:" -ForegroundColor Yellow
Write-Host ""

aws cloudformation describe-stacks `
  --stack-name $stackName `
  --profile $profile `
  --region $region `
  --query "Stacks[0].Outputs" `
  --output table

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Deployment complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Copy these values to frontend/.env:" -ForegroundColor Cyan
Write-Host "  VITE_API_BASE_URL = <ApiUrl from table above>" -ForegroundColor White
Write-Host "  VITE_COGNITO_USER_POOL_ID = <CognitoUserPoolId>" -ForegroundColor White
Write-Host "  VITE_COGNITO_CLIENT_ID = <CognitoUserPoolClientId>" -ForegroundColor White
