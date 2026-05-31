"""
S3 utilities: presigned URLs, thumbnail generation, video frame extraction.
"""
import os
import io
import hashlib
import logging
from typing import Tuple

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

S3_BUCKET = os.getenv("S3_BUCKET", "aussie-ecolens-g62")
PRESIGNED_EXPIRY = int(os.getenv("PRESIGNED_EXPIRY", "300"))  # 5 minutes

s3 = boto3.client("s3", config=Config(signature_version="s3v4"))


def generate_presigned_upload(object_key: str, content_type: str,
                              checksum_sha256: str) -> dict:
    """Generate a presigned URL for S3 upload with checksum validation."""
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": S3_BUCKET,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=PRESIGNED_EXPIRY,
    )
    return {
        "uploadUrl": url,
        "objectKey": object_key,
        "bucket": S3_BUCKET,
        "expiresIn": PRESIGNED_EXPIRY,
    }


def generate_presigned_get(object_key: str, expiry: int = 3600) -> str:
    """Generate a presigned URL for reading an S3 object."""
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": object_key},
        ExpiresIn=expiry,
    )


def compute_s3_checksum(bucket: str, key: str) -> str:
    """Compute SHA256 checksum of an S3 object (after upload)."""
    resp = s3.get_object(Bucket=bucket, Key=key)
    body = resp["Body"].read()
    return hashlib.sha256(body).hexdigest()


def delete_s3_object(key: str):
    """Delete a single object from S3."""
    s3.delete_object(Bucket=S3_BUCKET, Key=key)


def delete_s3_prefix(prefix: str):
    """Delete all objects under a prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        objects = page.get("Contents", [])
        if objects:
            s3.delete_objects(
                Bucket=S3_BUCKET,
                Delete={"Objects": [{"Key": o["Key"]} for o in objects]},
            )


# ==================== Thumbnail & Frame Processing ====================

def generate_thumbnail(image_data: bytes, max_width: int = 320,
                       max_height: int = 240) -> bytes:
    """Resize image maintaining aspect ratio, compress as JPEG."""
    import cv2
    import numpy as np

    img_array = np.frombuffer(image_data, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image for thumbnail")

    h, w = img.shape[:2]
    scale = min(max_width / w, max_height / h, 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    _, buf = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return buf.tobytes()


def extract_video_frames(video_data: bytes, fps: int = 1) -> list:
    """Extract 1 frame per second from video. Returns list of (second, jpg_bytes)."""
    import cv2
    import numpy as np
    import tempfile
    import os

    # Write video to temp file (OpenCV needs a file path)
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_data)
        tmp_path = tmp.name

    frames = []
    try:
        cap = cv2.VideoCapture(tmp_path)
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_interval = int(video_fps / fps) if video_fps >= fps else 1

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_interval == 0:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                second = frame_idx / video_fps
                frames.append((int(second), buf.tobytes()))
            frame_idx += 1
        cap.release()
    finally:
        os.unlink(tmp_path)

    return frames
