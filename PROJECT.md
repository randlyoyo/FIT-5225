# AussieEcoLens — Project Overview

## Architecture

```
User Browser (React + Vite)
  │
  ├── Cognito Auth ──────── AWS Cognito
  │
  ├── REST API ──────────── AWS API Gateway ── Lambda (api_handler)
  │                              │
  ├── S3 Presigned Upload ───────┤
  │                              │
  └── Query By File ──────────── GCP Cloud Run (/v1/query/by-file)
                                 │
                      ┌──────────┘
                      │
          S3 Event ───┴──→ Lambda (process_handler)
                              │
                              ├── GCP Cloud Run (/internal/infer)
                              ├── DynamoDB (Files, MediaTags, TagSubscriptions)
                              └── SNS (email notifications)
```

## Project Structure

```
├── frontend/            React + Vite + TypeScript + Ant Design
│   ├── src/
│   │   ├── api/         API client (AWS + GCP)
│   │   ├── auth/        Cognito auth context, protected routes
│   │   ├── components/  Shared components (Layout)
│   │   ├── pages/       Login, Register, Upload, Query, Manage, Notifications
│   │   └── types/       TypeScript type definitions
│   └── ...
├── aws-lambdas/         Python Lambda functions
│   ├── api_handler/     REST API router (11 endpoints)
│   ├── process_handler/ S3 event → thumbnail, frames, ML tagging, DB insert
│   └── shared/          DynamoDB, S3, SNS utilities
├── gcp-cloud-run/       Cloud Run ML inference service (FastAPI)
│   ├── main.py          Routes: /v1/query/by-file, /internal/infer
│   ├── auth.py          JWT (Cognito) + shared secret auth
│   ├── model_handler.py MegaDetector + SpeciesNet pipeline
│   ├── config.py        Environment-based configuration
│   └── Dockerfile       Python 3.12-slim + PyTorch + OpenCV
├── infra/               AWS CloudFormation template
├── scripts/             Deployment scripts
└── docs/                Reports (to be added)
```

## Quick Start

### Prerequisites
- Node.js 22+ & npm
- Python 3.12+
- Docker
- gcloud CLI
- AWS credentials (when available)

### GCP Cloud Run (working now)
```bash
cd gcp-cloud-run
pip install -r requirements.txt
DEV_MODE=true python main.py  # Local dev with mock models
```

Deploy:
```bash
bash scripts/deploy-gcp.sh
```

### Frontend (working now, mock mode)
```bash
cd frontend
cp .env.example .env  # Edit with your values
npm install
npm run dev            # http://localhost:5173
```

### AWS Lambda (code ready, needs AWS credentials to deploy)
```bash
bash scripts/deploy-aws.sh
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/uploads/init | Generate presigned upload URL |
| POST | /v1/uploads/complete | Confirm upload completion |
| GET | /v1/files/{fileId} | Get file record |
| POST | /v1/query/tags | Multi-tag AND query with min counts |
| POST | /v1/query/species | Species query (count ≥ 1) |
| POST | /v1/query/thumbnail | Find full-size image by thumbnail URL |
| POST | /v1/tags/bulk | Bulk add/remove tags |
| POST | /v1/files/delete | Delete files from S3 + DB |
| POST | /v1/notifications/subscriptions | Subscribe to tag notifications |
| GET | /v1/notifications/subscriptions | List subscriptions |
| DELETE | /v1/notifications/subscriptions/{id} | Unsubscribe |
| POST | /v1/query/by-file | (GCP) Query by uploaded file |
| POST | /internal/infer | (GCP) Internal ML inference |

## Database Schema

### Files Table
PK: `fileId` | GSIs: `ownerSub-checksum-index`, `fileUrl-index`, `thumbnailUrl-index`, `ownerSub-index`

### MediaTags Table
PK: `tagName`, SK: `fileId` | Enables AND queries via intersection

### TagSubscriptions Table
PK: `subscriptionId` | GSIs: `ownerSub-index`, `tagName-index`
