$apiId = "bgxu6v2h6f"
$region = "us-east-1"
$profile = "aussie-ecolens"

$corsParams = @{
    "gatewayresponse.header.Access-Control-Allow-Origin" = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'GET,POST,DELETE,OPTIONS'"
}

$responseTypes = @("UNAUTHORIZED", "ACCESS_DENIED", "DEFAULT_4XX", "DEFAULT_5XX")

foreach ($type in $responseTypes) {
    Write-Host "Setting gateway response: $type" -ForegroundColor Yellow
    $paramsJson = ($corsParams.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ","
    $cliParams = $corsParams.Keys | ForEach-Object { "$_=$($corsParams[$_])" }
    aws apigateway put-gateway-response `
      --rest-api-id $apiId `
      --response-type $type `
      --response-parameters $cliParams `
      --region $region `
      --profile $profile
}

Write-Host "Redeploying..." -ForegroundColor Yellow
aws apigateway create-deployment --rest-api-id $apiId --stage-name prod --region $region --profile $profile

Write-Host "Done!" -ForegroundColor Green
