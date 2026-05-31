#!/bin/bash
API_ID="bgxu6v2h6f"
REGION="us-east-1"
PROFILE="aussie-ecolens"

for TYPE in UNAUTHORIZED ACCESS_DENIED DEFAULT_4XX DEFAULT_5XX; do
  echo "Setting gateway response: $TYPE"
  aws apigateway put-gateway-response \
    --rest-api-id "$API_ID" \
    --response-type "$TYPE" \
    --response-parameters '{"gatewayresponse.header.Access-Control-Allow-Origin":"'"'"'*'"'"'","gatewayresponse.header.Access-Control-Allow-Headers":"'"'"'Content-Type,Authorization'"'"'"}' \
    --region "$REGION" \
    --profile "$PROFILE"
done

echo "Redeploying..."
aws apigateway create-deployment --rest-api-id "$API_ID" --stage-name prod --region "$REGION" --profile "$PROFILE"
echo "Done!"
