$bucket = "aussie-ecolens-g62-prod"
$region = "us-east-1"
$profile = "aussie-ecolens"

Write-Host "Setting public-read + Lambda access policy on $bucket ..." -ForegroundColor Yellow

$policy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::$bucket/*"
    }
  ]
}
"@

$policyPath = "$PWD\s3-policy-temp.json"
[System.IO.File]::WriteAllText($policyPath, $policy, [System.Text.UTF8Encoding]::new($false))

aws s3api put-public-access-block `
  --bucket $bucket `
  --public-access-block-configuration BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false `
  --region $region --profile $profile

aws s3api put-bucket-policy `
  --bucket $bucket `
  --policy "file://$policyPath" `
  --region $region --profile $profile

Remove-Item $policyPath -Force -ErrorAction SilentlyContinue

if ($LASTEXITCODE -eq 0) {
    Write-Host "Done! Try: http://aussie-ecolens-g62-prod.s3-website-us-east-1.amazonaws.com" -ForegroundColor Green
} else {
    Write-Host "Failed." -ForegroundColor Red
}
