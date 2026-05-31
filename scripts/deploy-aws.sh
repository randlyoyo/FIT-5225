#!/bin/bash
# Package and deploy AussieEcoLens AWS infrastructure
# Run from repository root
set -e

S3_DEPLOY_BUCKET="${S3_DEPLOY_BUCKET:-aussie-ecolens-deploy-g62}"
STACK_NAME="${STACK_NAME:-AussieEcoLens}"
ENV="${ENV:-prod}"
AWS_PROFILE="${AWS_PROFILE:-aussie-ecolens}"

echo "==> Installing Lambda layer dependencies..."
cd aws-lambdas
pip install -r requirements.txt -t layer/python --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 2>&1 | tail -3
cd ..

echo "==> Packaging Lambda zip files..."
python3 -c "
import zipfile, os
base = 'aws-lambdas'
for handler in ['api_handler', 'process_handler']:
    os.makedirs(f'{base}/lambdas', exist_ok=True)
    with zipfile.ZipFile(f'{base}/lambdas/{handler}.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(f'{base}/{handler}/lambda_function.py', 'lambda_function.py')
        for root, dirs, files in os.walk(f'{base}/shared'):
            for f in files:
                path = os.path.join(root, f)
                z.write(path, os.path.relpath(path, base))
    size = os.path.getsize(f'{base}/lambdas/{handler}.zip')
    print(f'  {handler}.zip: {size} bytes')
"

echo "==> Packaging Lambda layer (dependencies)..."
python3 -c "
import zipfile, os, shutil
base = 'aws-lambdas'
layer_dir = f'{base}/layer'
os.makedirs(f'{base}/lambdas', exist_ok=True)
layer_zip = f'{base}/lambdas/layer.zip'
if os.path.exists(layer_zip):
    os.remove(layer_zip)
with zipfile.ZipFile(layer_zip, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(layer_dir):
        for f in files:
            path = os.path.join(root, f)
            arcname = os.path.relpath(path, base)
            z.write(path, arcname)
size = os.path.getsize(layer_zip)
print(f'  layer.zip: {size} bytes')
"

echo "==> Uploading Lambda code to S3..."
aws s3 cp aws-lambdas/lambdas/api_handler.zip "s3://${S3_DEPLOY_BUCKET}/lambdas/api_handler.zip" --profile "$AWS_PROFILE"
aws s3 cp aws-lambdas/lambdas/process_handler.zip "s3://${S3_DEPLOY_BUCKET}/lambdas/process_handler.zip" --profile "$AWS_PROFILE"
aws s3 cp aws-lambdas/lambdas/layer.zip "s3://${S3_DEPLOY_BUCKET}/lambdas/layer.zip" --profile "$AWS_PROFILE"

echo "==> Deploying CloudFormation stack..."
aws cloudformation deploy \
  --template-file infra/cloudformation.yaml \
  --stack-name "$STACK_NAME" \
  --parameter-overrides \
    Environment="$ENV" \
    GCPInferUrl="${GCP_INFER_URL:-https://example.com}" \
    GCPInternalSecret="${GCP_INTERNAL_SECRET:-change-me-in-production}" \
    LambdaDeployBucket="$S3_DEPLOY_BUCKET" \
  --capabilities CAPABILITY_IAM \
  --profile "$AWS_PROFILE"

echo "==> Stack outputs:"
aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --profile "$AWS_PROFILE" \
  --query "Stacks[0].Outputs" \
  --output table

echo ""
echo "==> Deployment complete!"
echo "    Frontend env vars to set:"
echo "    VITE_API_BASE_URL=<ApiUrl from above>"
echo "    VITE_COGNITO_USER_POOL_ID=<CognitoUserPoolId from above>"
echo "    VITE_COGNITO_CLIENT_ID=<CognitoUserPoolClientId from above>"
