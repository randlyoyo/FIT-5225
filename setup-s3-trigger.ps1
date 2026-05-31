$bucket = "aussie-ecolens-g62-prod"
$region = "us-east-1"
$profile = "aussie-ecolens"

$json = @'
{
  "LambdaFunctionConfigurations": [
    {
      "LambdaFunctionArn": "arn:aws:lambda:us-east-1:477216322118:function:AussieEcoLens-Process-prod",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "originals/"
            }
          ]
        }
      }
    }
  ]
}
'@

$path = "$PWD\s3-notify.json"
[System.IO.File]::WriteAllText($path, $json, [System.Text.UTF8Encoding]::new($false))

Write-Host "Setting S3 notification on $bucket ..." -ForegroundColor Yellow
aws s3api put-bucket-notification-configuration --bucket $bucket --notification-configuration "file://$path" --region $region --profile $profile

if ($LASTEXITCODE -eq 0) {
    Write-Host "S3 trigger configured!" -ForegroundColor Green
} else {
    Write-Host "Failed. See error above." -ForegroundColor Red
}
