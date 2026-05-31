"""
AussieEcoLens — Cloud Run ML Inference Service

Dual entry-point:
  POST /v1/query/by-file   (user JWT) — query-by-file, temporary inference
  POST /internal/infer      (shared secret) — Lambda triggered processing

Health: GET /health — confirms service is alive + models loaded.
"""
import logging
import traceback
from io import BytesIO
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Request, HTTPException, Depends
from fastapi.responses import JSONResponse

from config import DEV_MODE, AWS_API_BASE_URL
from auth import verify_cognito_jwt, verify_internal_secret, get_user_jwt
from model_handler import get_pipeline

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cloud-run-ml")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AussieEcoLens ML Service",
    version="1.0.0",
    docs_url=None if not DEV_MODE else "/docs",
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Startup: preload models
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    """Preload ML models at container start (takes advantage of min-instances=1)."""
    logger.info("Starting model preload...")
    try:
        pipeline = get_pipeline()
        pipeline.load_models()
        logger.info("Models loaded successfully")
    except Exception as e:
        logger.error(
            "Model preload failed: %s. Service will start but "
            "inference requests will fail until models are available.", e
        )
        # Never crash startup — let individual requests handle the error


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "healthy", "dev_mode": DEV_MODE}


# ---------------------------------------------------------------------------
# User-facing: Query by File  (JWT auth)
# ---------------------------------------------------------------------------

@app.post("/v1/query/by-file")
async def query_by_file(request: Request, file: bytes = File(...)):
    """
    Accept a file, run ML inference, query AWS for matching DB files.

    The uploaded file is NOT stored permanently.
    Returns list of matching file URLs from the database.
    """
    token = get_user_jwt(request)
    claims = verify_cognito_jwt(token)
    user_sub = claims.get("sub", "unknown")
    logger.info(f"query-by-file: user={user_sub}, size={len(file)} bytes")

    # Decode image
    try:
        img_array = np.frombuffer(file, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail="Unsupported image format")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode uploaded file")

    # Run inference
    pipeline = get_pipeline()
    try:
        if DEV_MODE and not pipeline.detector.model:
            tag_counts = pipeline.predict_mock(image)
        else:
            tag_counts = pipeline.predict(image)
    except Exception as e:
        logger.error("Query-by-file inference failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Model inference failed: {str(e)}. "
                   "If running locally, set DEV_MODE=true for mock models.",
        )

    logger.info("Detected tags: %s", tag_counts)

    # Query AWS API for matching files
    matching_urls = await _query_aws_tags(tag_counts, token)

    return {
        "queryTags": tag_counts,
        "matchingFiles": matching_urls,
        "count": len(matching_urls),
    }


async def _query_aws_tags(tag_counts: dict, token: str) -> list:
    """
    Call AWS API Gateway /v1/query/tags with detected tags.
    Returns list of matching file records.
    """
    if not AWS_API_BASE_URL:
        logger.warning("AWS_API_BASE_URL not configured; returning empty results")
        return []

    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{AWS_API_BASE_URL}/v1/query/tags",
                json={"tags": tag_counts},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json().get("files", [])
    except Exception as e:
        logger.error(f"Failed to query AWS: {e}")
        return []


# ---------------------------------------------------------------------------
# Internal: Lambda-triggered inference  (shared secret auth)
# ---------------------------------------------------------------------------

@app.post("/internal/infer")
async def internal_infer(request: Request):
    """
    Internal endpoint called by AWS Lambda (S3 processing trigger).

    Expects JSON body:
      {
        "fileUrl": "https://s3.../originals/images/xxx.jpg",
        "fileId": "uuid",
        "fileType": "image" | "video"
      }

    Returns:
      {
        "fileId": "uuid",
        "tagCounts": {"kangaroo": 2, ...},
        "modelVersion": "mdv5a+speciesnet-v1"
      }
    """
    verify_internal_secret(request)

    body = await request.json()
    file_url = body.get("fileUrl")
    file_id = body.get("fileId")
    file_type = body.get("fileType", "image")

    if not file_url or not file_id:
        raise HTTPException(status_code=400, detail="Missing fileUrl or fileId")

    logger.info(f"internal/infer: fileId={file_id}, type={file_type}")

    # Download image from S3 URL
    try:
        image = await _download_image(file_url)
    except Exception as e:
        logger.error(f"Failed to download {file_url}: {e}")
        return {
            "fileId": file_id,
            "error": f"Download failed: {str(e)}",
            "tagCounts": {},
            "modelVersion": "mdv5a+speciesnet-v1",
        }

    # Run inference
    pipeline = get_pipeline()
    try:
        if DEV_MODE and not pipeline.detector.model:
            tag_counts = pipeline.predict_mock(image)
        else:
            tag_counts = pipeline.predict(image)
    except Exception as e:
        logger.error("Inference failed for %s: %s", file_id, e)
        return {
            "fileId": file_id,
            "error": f"Inference failed: {str(e)}",
            "tagCounts": {},
            "modelVersion": "mdv5a+speciesnet-v1",
        }

    logger.info("fileId=%s tagCounts=%s", file_id, tag_counts)

    return {
        "fileId": file_id,
        "tagCounts": tag_counts,
        "modelVersion": "mdv5a+speciesnet-v1",
    }


async def _download_image(url: str) -> np.ndarray:
    """Download an image from S3 URL and decode as OpenCV BGR numpy array."""
    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        img_array = np.frombuffer(resp.content, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Failed to decode downloaded image")
        return image


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error("Unhandled error: %s\n%s", exc, traceback.format_exc())
    detail = f"{type(exc).__name__}: {exc}" if DEV_MODE else "Internal server error"
    return JSONResponse(
        status_code=500,
        content={"error": detail},
    )


# ---------------------------------------------------------------------------
# Entry point (for local dev)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
