"""
S3 Event → Lambda: File Processing Handler

Triggered by S3 ObjectCreated events on originals/ prefix.
Handles:
  - Image: generate thumbnail, call GCP ML for tagging
  - Video: extract frames 1fps, call GCP ML on each frame, aggregate tags
  - Write results to DynamoDB (Files + MediaTags)
  - Publish SNS notifications for new tags
"""
import os
import json
import logging
import traceback
import urllib.parse
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3
from shared import db, s3_utils, sns_utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

S3_BUCKET = os.getenv("S3_BUCKET", "aussie-ecolens-g62")
GCP_INFER_URL = os.getenv("GCP_INFER_URL", "")
GCP_INTERNAL_SECRET = os.getenv("GCP_INTERNAL_SECRET", "")
MAX_VIDEO_SECONDS = int(os.getenv("MAX_VIDEO_SECONDS", "60"))
INFER_CONCURRENCY = int(os.getenv("INFER_CONCURRENCY", "5"))

s3 = boto3.client("s3")


def lambda_handler(event: dict, context):
    """Process S3 event: one record per uploaded file."""
    results = []

    for record in event.get("Records", []):
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name", S3_BUCKET)
        object_key = urllib.parse.unquote_plus(
            s3_info.get("object", {}).get("key", "")
        )
        logger.info(f"Processing: s3://{bucket}/{object_key}")

        try:
            result = process_file(bucket, object_key)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to process {object_key}: {traceback.format_exc()}")
            results.append({"objectKey": object_key, "error": str(e)})

    return {"processed": results}


def process_file(bucket: str, object_key: str) -> dict:
    """Process a single uploaded file."""
    # Determine file type from path
    file_type = "video" if "/videos/" in object_key else "image"

    # Download file from S3
    resp = s3.get_object(Bucket=bucket, Key=object_key)
    file_data = resp["Body"].read()
    content_type = resp.get("ContentType", "image/jpeg")

    # Find the file record by object_key
    file_record = _find_record_by_key(object_key)
    if not file_record:
        logger.warning(f"No DynamoDB record found for {object_key}, creating one...")
        # This shouldn't happen in normal flow (record created at upload init)
        # But handle gracefully
        return {"objectKey": object_key, "status": "skipped", "reason": "no db record"}

    file_id = file_record["fileId"]
    file_url = file_record.get("fileUrl", "")

    try:
        if file_type == "image":
            result = process_image(bucket, file_id, file_url, file_data, file_record)
        else:
            result = process_video(bucket, file_id, file_url, file_data, file_record)
        return result
    except Exception as e:
        db.update_file_status(file_id, "error", errorMessage=str(e))
        raise


def process_image(bucket: str, file_id: str, file_url: str,
                  file_data: bytes, record: dict) -> dict:
    """Process an uploaded image: thumbnail + ML tagging."""
    # 1. Generate thumbnail
    thumb_key = None
    thumbnail_url = None
    try:
        thumb_bytes = s3_utils.generate_thumbnail(file_data)
        thumb_key = f"thumbnails/images/{file_id}.jpg"
        s3.put_object(
            Bucket=bucket,
            Key=thumb_key,
            Body=thumb_bytes,
            ContentType="image/jpeg",
        )
        thumbnail_url = f"https://{bucket}.s3.amazonaws.com/{thumb_key}"
    except Exception as e:
        logger.error(f"Thumbnail generation failed: {e}")

    # 2. Call GCP ML inference (use presigned URL for GCP to access private S3 file)
    presigned_url = s3_utils.generate_presigned_get(record.get("objectKey", ""))
    tag_counts = _call_gcp_inference(presigned_url, file_id, "image")

    # 3. Write to database
    db.update_file_status(
        file_id,
        "ready",
        thumbnailKey=thumb_key,
        thumbnailUrl=thumbnail_url,
        tagCounts=tag_counts,
        autoTagCounts=tag_counts,
        modelVersion="mdv5a+speciesnet-v1",
    )

    # 4. Write MediaTags
    if tag_counts:
        db.update_media_tags(file_id, "image", file_url, thumbnail_url, tag_counts)

    # 5. Notify subscribers
    for tag in tag_counts:
        sns_utils.publish_tag_notification(
            tag, file_url, thumbnail_url, tag_counts[tag],
        )

    logger.info(f"Image {file_id} processed: {tag_counts}")
    return {"fileId": file_id, "status": "ready", "tagCounts": tag_counts}


def _upload_frame_to_s3(bucket: str, file_id: str, second: int,
                        frame_bytes: bytes) -> tuple:
    """Upload a single frame + thumbnail to S3. Returns (frame_key, thumb_key, frame_url)."""
    # Upload frame
    frame_key = f"frames/{file_id}/frame_{second}.jpg"
    s3.put_object(
        Bucket=bucket, Key=frame_key,
        Body=frame_bytes, ContentType="image/jpeg",
    )

    # Generate frame thumbnail
    thumb_key = ""
    try:
        frame_thumb_bytes = s3_utils.generate_thumbnail(frame_bytes)
        thumb_key = f"thumbnails/frames/{file_id}/frame_{second}.jpg"
        s3.put_object(
            Bucket=bucket, Key=thumb_key,
            Body=frame_thumb_bytes, ContentType="image/jpeg",
        )
    except Exception:
        pass

    # Use presigned URL so GCP Cloud Run can access the private S3 object
    frame_url = s3_utils.generate_presigned_get(frame_key)
    return frame_key, thumb_key, frame_url


def process_video(bucket: str, file_id: str, file_url: str,
                  file_data: bytes, record: dict) -> dict:
    """Process an uploaded video: extract frames, upload+infer concurrently, aggregate results."""
    # 1. Extract frames (1 fps), capped at MAX_VIDEO_SECONDS
    all_frames = s3_utils.extract_video_frames(file_data, fps=1)
    frames = all_frames[:MAX_VIDEO_SECONDS]

    if len(all_frames) > MAX_VIDEO_SECONDS:
        logger.warning(
            f"Video {file_id}: truncated to {MAX_VIDEO_SECONDS}s "
            f"(original: {len(all_frames)} frames)"
        )

    logger.info(f"Video {file_id}: {len(frames)} frames to process")

    # 2. Upload frames to S3 in parallel
    frame_keys = []
    frame_thumb_keys = []
    frame_urls = []

    with ThreadPoolExecutor(max_workers=INFER_CONCURRENCY) as pool:
        upload_futures = {
            pool.submit(_upload_frame_to_s3, bucket, file_id, second, frame_bytes): second
            for second, frame_bytes in frames
        }
        for future in as_completed(upload_futures):
            try:
                fk, tk, furl = future.result()
                frame_keys.append(fk)
                if tk:
                    frame_thumb_keys.append(tk)
                frame_urls.append((upload_futures[future], furl))
            except Exception as e:
                logger.error(f"Frame upload failed at second {upload_futures[future]}: {e}")

    # 3. Run GCP inference on each frame in parallel
    all_tags = {}
    frame_urls.sort()  # Sort by second for deterministic logging

    with ThreadPoolExecutor(max_workers=INFER_CONCURRENCY) as pool:
        infer_futures = {
            pool.submit(
                _call_gcp_inference, furl, f"{file_id}_f{second}", "image"
            ): second
            for second, furl in frame_urls
        }
        for future in as_completed(infer_futures):
            second = infer_futures[future]
            try:
                frame_tags = future.result(timeout=60)
                for tag, count in frame_tags.items():
                    all_tags[tag] = max(all_tags.get(tag, 0), count)
            except Exception as e:
                logger.error(f"Inference failed for frame at {second}s: {e}")

    # 4. Write results to DynamoDB
    if all_tags:
        db.update_file_status(
            file_id,
            "ready",
            frameKeys=frame_keys,
            frameThumbnailKeys=frame_thumb_keys,
            tagCounts=all_tags,
            autoTagCounts=all_tags,
            modelVersion="mdv5a+speciesnet-v1",
        )
        db.update_media_tags(file_id, "video", file_url, file_url, all_tags)
    else:
        db.update_file_status(
            file_id, "ready",
            frameKeys=frame_keys,
            frameThumbnailKeys=frame_thumb_keys,
            tagCounts={},
            autoTagCounts={},
            modelVersion="mdv5a+speciesnet-v1",
        )

    # 5. Notify subscribers
    for tag, count in all_tags.items():
        try:
            sns_utils.publish_tag_notification(tag, file_url, file_url, count)
        except Exception as e:
            logger.error(f"Notification failed for tag {tag}: {e}")

    logger.info(
        f"Video {file_id}: {len(frames)} frames, {len(frame_thumb_keys)} thumbnails, "
        f"tags={all_tags}"
    )
    return {"fileId": file_id, "status": "ready", "frames": len(frames), "tagCounts": all_tags}


def _call_gcp_inference(file_url: str, file_id: str, file_type: str) -> dict:
    """Call GCP Cloud Run /internal/infer with shared secret."""
    if not GCP_INFER_URL:
        logger.warning("GCP_INFER_URL not set; using mock tags")
        return {}

    import urllib.request

    body = json.dumps({
        "fileUrl": file_url,
        "fileId": file_id,
        "fileType": file_type,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{GCP_INFER_URL}/internal/infer",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Internal-Secret": GCP_INTERNAL_SECRET,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result.get("tagCounts", {})
    except Exception as e:
        logger.error(f"GCP inference failed: {e}")
        return {}


def _find_record_by_key(object_key: str) -> Optional[dict]:
    """Find Files table record by objectKey by scanning with pagination."""
    paginator = db.files_tbl.meta.client.get_paginator("scan")
    for page in paginator.paginate(
        TableName=db.FILES_TABLE,
        FilterExpression=boto3.dynamodb.conditions.Attr("objectKey").eq(object_key),
        Limit=500,
    ):
        for item in page.get("Items", []):
            return item
    return None
