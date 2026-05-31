# ============================================================
#  AussieEcoLens 完整部署脚本
#  用法: .\deploy-all.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$region   = "us-east-1"
$profile  = "aussie-ecolens"
$s3bucket = "aussie-ecolens-g62-prod"
$gcpUrl   = "https://aussie-ecolens-ml-1029582539414.us-central1.run.app"
$gcpSecret = "aussie-ecolens-secret-2026"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AussieEcoLens 完整部署" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# Step 1: 更新 Lambda 环境变量
# ============================================================
Write-Host "[1/4] 更新 AWS Lambda 环境变量..." -ForegroundColor Yellow

$envVars = @{
    S3_BUCKET            = $s3bucket
    FILES_TABLE          = "AussieEcoLens-Files-prod"
    MEDIA_TAGS_TABLE     = "AussieEcoLens-MediaTags-prod"
    TAG_SUBS_TABLE       = "AussieEcoLens-TagSubscriptions-prod"
    SNS_TOPIC_ARN        = "arn:aws:sns:us-east-1:477216322118:AussieEcoLens-Notifications-prod"
    GCP_INFER_URL        = $gcpUrl
    GCP_INTERNAL_SECRET  = $gcpSecret
}
$envString = ($envVars.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ","

aws lambda update-function-configuration `
  --function-name AussieEcoLens-API-prod `
  --environment "Variables={$envString}" `
  --region $region --profile $profile | Out-Null
Write-Host "  API Lambda ................... OK" -ForegroundColor Green

aws lambda update-function-configuration `
  --function-name AussieEcoLens-Process-prod `
  --environment "Variables={$envString}" `
  --region $region --profile $profile | Out-Null
Write-Host "  Process Lambda ............... OK" -ForegroundColor Green

# ============================================================
# Step 2: 配置 S3 事件触发
# ============================================================
Write-Host "[2/4] 配置 S3 事件触发..." -ForegroundColor Yellow

$notifyJson = @"
{
  "LambdaFunctionConfigurations": [
    {
      "LambdaFunctionArn": "arn:aws:lambda:us-east-1:477216322118:function:AussieEcoLens-Process-prod",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [{"Name": "prefix", "Value": "originals/"}]
        }
      }
    }
  ]
}
"@

$notifyPath = "$PWD\s3-notify-temp.json"
[System.IO.File]::WriteAllText($notifyPath, $notifyJson, [System.Text.UTF8Encoding]::new($false))

aws s3api put-bucket-notification-configuration `
  --bucket $s3bucket `
  --notification-configuration "file://$notifyPath" `
  --region $region --profile $profile
Remove-Item $notifyPath -Force -ErrorAction SilentlyContinue
Write-Host "  S3 trigger ................... OK" -ForegroundColor Green

# ============================================================
# Step 3: 构建前端 + 上传到 S3
# ============================================================
Write-Host "[3/4] 构建前端 + 部署到 S3..." -ForegroundColor Yellow

Set-Location $PSScriptRoot/frontend

# 写 .env
@"
VITE_AWS_REGION=us-east-1
VITE_COGNITO_USER_POOL_ID=us-east-1_X2Cb0Asro
VITE_COGNITO_CLIENT_ID=1flocbu40ocf44ljrggesbvtgo
VITE_API_BASE_URL=https://bgxu6v2h6f.execute-api.us-east-1.amazonaws.com/prod
VITE_GCP_BASE_URL=$gcpUrl
VITE_S3_BUCKET=$s3bucket
"@ | Out-File -FilePath .env -Encoding utf8

Write-Host "  .env ......................... OK" -ForegroundColor Green
Write-Host "  npm run build ... (may take 1-2 min)" -ForegroundColor Gray

npm run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  Build ........................ OK" -ForegroundColor Green

aws s3 sync dist/ "s3://$s3bucket/" --region $region --profile $profile --delete
Write-Host "  Upload to S3 ................. OK" -ForegroundColor Green

Set-Location $PSScriptRoot

# ============================================================
# Step 4: 验证
# ============================================================
Write-Host "[4/4] 验证部署..." -ForegroundColor Yellow

Write-Host "  GCP Health: $(curl.exe -s $gcpUrl/health 2>$null)" -ForegroundColor Gray

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  部署完成!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  前端地址: http://aussie-ecolens-g62-prod.s3-website-us-east-1.amazonaws.com" -ForegroundColor White
Write-Host "  API 地址: https://bgxu6v2h6f.execute-api.us-east-1.amazonaws.com/prod" -ForegroundColor White
Write-Host "  GCP  地址: $gcpUrl" -ForegroundColor White
Write-Host ""
Write-Host "  验收步骤:" -ForegroundColor Cyan
Write-Host "  1. 打开前端地址 -> 注册 -> 邮箱验证 -> 登录" -ForegroundColor White
Write-Host "  2. 上传一张图片 -> 等 processing -> Query 查到结果" -ForegroundColor White
Write-Host "  3. Manage 页面 -> bulk tag / delete" -ForegroundColor White
Write-Host "  4. Notifications -> 订阅 -> 收到 SNS 邮件" -ForegroundColor White
