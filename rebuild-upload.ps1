Set-Location D:\Study\Monash\5225\A2\frontend
Write-Host "Building..." -ForegroundColor Yellow
npm run build
if ($LASTEXITCODE -ne 0) { Write-Host "Build failed!" -ForegroundColor Red; exit 1 }
Write-Host "Uploading to S3..." -ForegroundColor Yellow
aws s3 sync dist/ s3://aussie-ecolens-g62-prod/ --region us-east-1 --profile aussie-ecolens --delete
Write-Host "Done!" -ForegroundColor Green
