"""
Centralised configuration for Cloud Run ML service.
All values read from environment variables with sensible defaults.
"""
import os
import logging

logger = logging.getLogger(__name__)


# --- GCS Model Storage ---
GCS_BUCKET = os.getenv("GCS_BUCKET", "aussie-ecolens-g62-models")
MODEL_BASE_PATH = os.getenv("MODEL_BASE_PATH", "current")
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "/tmp/models")

# Individual model files (relative to GCS_BUCKET/MODEL_BASE_PATH)
MEGADETECTOR_MODEL = os.getenv("MEGADETECTOR_MODEL", "mdv5a.pt")
SPECIESNET_MODEL = os.getenv("SPECIESNET_MODEL", "model.pt")
SPECIESNET_LABELS = os.getenv("SPECIESNET_LABELS", "labels.txt")

# --- Auth ---
COGNITO_REGION = os.getenv("COGNITO_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
# JWKS URL: constructed from region + pool ID
COGNITO_JWKS_URL = os.getenv(
    "COGNITO_JWKS_URL",
    f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json",
)

# Shared secret for internal Lambda -> Cloud Run calls
INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "change-me-in-production")
INTERNAL_SECRET_HEADER = "X-Internal-Secret"

# --- AWS API Gateway (for query-by-file to call back) ---
AWS_API_BASE_URL = os.getenv("AWS_API_BASE_URL", "")

# --- Inference ---
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

# --- Server ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))


# --- Startup validation ---
def validate_config():
    """Validate critical configuration on startup. Returns list of warnings."""
    warnings = []

    if not DEV_MODE:
        if INTERNAL_API_SECRET == "change-me-in-production":
            warnings.append(
                "INTERNAL_API_SECRET is still the default value "
                "- internal endpoints are insecure!"
            )
        if not COGNITO_USER_POOL_ID:
            warnings.append(
                "COGNITO_USER_POOL_ID is not set - JWT verification will fail"
            )
        if not AWS_API_BASE_URL:
            warnings.append(
                "AWS_API_BASE_URL is not set - query-by-file will return empty results"
            )

    if warnings:
        for w in warnings:
            logger.warning("CONFIG WARNING: %s", w)
    else:
        logger.info("Configuration validated successfully")

    return warnings


# Auto-validate on import
_validation_warnings = validate_config()
