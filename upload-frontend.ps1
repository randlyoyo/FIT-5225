aws s3 sync D:\Study\Monash\5225\A2\frontend\dist\ s3://aussie-ecolens-g62-prod/ --region us-east-1 --profile aussie-ecolens --delete
if ($LASTEXITCODE -eq 0) { Write-Host "Upload OK" -ForegroundColor Green }
