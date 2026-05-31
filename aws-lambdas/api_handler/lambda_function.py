"""
API Gateway → Lambda handler for all AussieEcoLens REST endpoints.

Routes (API Gateway proxy integration):
  POST   /v1/uploads/init
  POST   /v1/uploads/complete
  GET    /v1/files/{fileId}
  POST   /v1/query/tags
  POST   /v1/query/species
  POST   /v1/query/thumbnail
  POST   /v1/tags/bulk
  POST   /v1/files/delete
  POST   /v1/notifications/subscriptions
  GET    /v1/notifications/subscriptions
  DELETE /v1/notifications/subscriptions/{subscriptionId}

Auth: API Gateway Cognito Authorizer passes claims via event.requestContext.authorizer.claims
"""
import os
import json
import logging
import traceback
import hashlib
import uuid
from typing import Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared import db, s3_utils, sns_utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

S3_BUCKET = os.getenv("S3_BUCKET", "aussie-ecolens-g62")
GCP_INFER_URL = os.getenv("GCP_INFER_URL", "")
GCP_INTERNAL_SECRET = os.getenv("GCP_INTERNAL_SECRET", "")
INTERNAL_SECRET_HEADER = "X-Internal-Secret"


# ==================== Helpers ====================

def _parse_body(event: dict) -> dict:
    body = event.get("body", "{}")
    if isinstance(body, str):
        return json.loads(body) if body else {}
    return body


def _get_user(event: dict) -> tuple:
    """Extract user sub and email from Cognito authorizer claims."""
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    return claims.get("sub", ""), claims.get("email", "")


def _ok(body: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
        },
        "body": json.dumps(body, default=str),
    }


def _err(message: str, status: int = 400) -> dict:
    return _ok({"error": message}, status)


def _route_key(event: dict) -> str:
    """Build a routing key from HTTP method + path."""
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")
    # Only normalise named path params (skip proxy catch-all)
    params = event.get("pathParameters") or {}
    for k, v in params.items():
        if k == "proxy":
            continue  # proxy captures the full path — use as-is
        path = path.replace(v, f"{{{k}}}")
    return f"{method} {path}"


# ==================== Route Handlers ====================

def handle_upload_init(event: dict) -> dict:
    """POST /v1/uploads/init — Generate presigned URL, check duplicates."""
    owner_sub, owner_email = _get_user(event)
    body = _parse_body(event)

    filename = body.get("filename", "")
    content_type = body.get("contentType", "image/jpeg")
    file_type = body.get("fileType", "image")
    size_bytes = int(body.get("sizeBytes", 0))
    checksum = body.get("checksumSha256", "")

    if not filename or not checksum:
        return _err("Missing filename or checksumSha256")

    # Dedup check
    existing = db.check_duplicate(owner_sub, checksum)
    if existing:
        return _ok({
            "duplicate": True,
            "existingFileId": existing.get("fileId"),
            "existingFileUrl": existing.get("fileUrl"),
            "message": "File already uploaded",
        })

    # Create file record
    file_id = str(uuid.uuid4())
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    folder = "images" if file_type == "image" else "videos"
    object_key = f"originals/{folder}/{file_id}.{ext}"
    file_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{object_key}"

    # Generate presigned URL
    presigned = s3_utils.generate_presigned_upload(object_key, content_type, checksum)

    # Create DynamoDB record
    db.create_file_record(
        file_id=file_id,
        owner_sub=owner_sub,
        owner_email=owner_email,
        original_filename=filename,
        file_type=file_type,
        content_type=content_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum,
        bucket=S3_BUCKET,
        object_key=object_key,
        file_url=file_url,
        status="uploading",
    )

    return _ok({
        "fileId": file_id,
        "uploadUrl": presigned["uploadUrl"],
        "objectKey": presigned["objectKey"],
        "expiresIn": presigned["expiresIn"],
        "duplicate": False,
    })


def handle_upload_complete(event: dict) -> dict:
    """POST /v1/uploads/complete — Verify upload, trigger processing."""
    owner_sub, _ = _get_user(event)
    body = _parse_body(event)

    file_id = body.get("fileId", "")
    object_key = body.get("objectKey", "")
    checksum = body.get("checksumSha256", "")

    if not file_id:
        return _err("Missing fileId")

    file_record = db.get_file(file_id)
    if not file_record:
        return _err("File not found", 404)

    # Verify checksum matches S3 object
    actual_checksum = s3_utils.compute_s3_checksum(S3_BUCKET, object_key)
    if checksum and actual_checksum != checksum:
        return _err("Checksum mismatch — file may be corrupted", 409)

    db.update_file_status(file_id, "processing")

    # S3 event will trigger process_handler Lambda automatically upon upload.
    # But if we want to be proactive, we can also invoke GCP directly here.
    # For now, S3 event is the primary trigger.

    return _ok({"fileId": file_id, "status": "processing"})


def handle_get_file(event: dict) -> dict:
    """GET /v1/files/{fileId}"""
    file_id = event.get("pathParameters", {}).get("fileId", "")
    record = db.get_file(file_id)
    if not record:
        return _err("File not found", 404)
    record = db._decimal_to_int(record)
    return _ok(record)


def handle_query_tags(event: dict) -> dict:
    """POST /v1/query/tags — Multi-tag AND query with min counts."""
    body = _parse_body(event)
    tags = body.get("tags", {})

    if not tags:
        return _err("Missing tags filter")

    files = db.query_files_by_tags(tags)
    return _ok({"files": files, "count": len(files)})


def handle_query_species(event: dict) -> dict:
    """POST /v1/query/species — Species query (count >= 1 for each)."""
    body = _parse_body(event)
    species = body.get("species", [])

    if not species:
        return _err("Missing species list")

    files = db.query_files_by_species(species)
    return _ok({"files": files, "count": len(files)})


def handle_query_thumbnail(event: dict) -> dict:
    """POST /v1/query/thumbnail — Given thumbnail URL, return full-size URL."""
    body = _parse_body(event)
    thumbnail_url = body.get("thumbnailUrl", "")

    if not thumbnail_url:
        return _err("Missing thumbnailUrl")

    file_record = db.find_file_by_thumbnail(thumbnail_url)
    if not file_record:
        return _err("No matching file found", 404)

    return _ok({
        "thumbnailUrl": thumbnail_url,
        "fullSizeUrl": file_record.get("fileUrl"),
        "fileId": file_record.get("fileId"),
        "fileType": file_record.get("fileType"),
    })


def handle_bulk_tags(event: dict) -> dict:
    """POST /v1/tags/bulk — Bulk add/remove tags on multiple files."""
    body = _parse_body(event)
    urls = body.get("urls", [])
    tags = body.get("tags", [])
    operation = body.get("operation", 1)  # 1=add, 0=remove

    if not urls or not tags:
        return _err("Missing urls or tags")

    files = db.query_files_by_urls(urls)
    results = []

    for f in files:
        file_id = f["fileId"]
        auto_tags = f.get("autoTagCounts", {}) or {}
        manual_tags = f.get("manualTagCounts", {}) or {}

        if operation == 1:  # add
            for tag in tags:
                manual_tags[tag] = manual_tags.get(tag, 0) + 1
        else:  # remove
            for tag in tags:
                # Remove from manual; if in auto, just do nothing
                manual_tags.pop(tag, None)
                # Also remove from MediaTags if present
                db.remove_media_tags(file_id, [tag])

        # Recalculate combined tagCounts (auto + manual, to avoid double-counting)
        combined = dict(auto_tags)
        for tag, count in manual_tags.items():
            combined[tag] = combined.get(tag, 0) + count

        db.update_file_status(file_id, f["status"],
                              manualTagCounts=manual_tags,
                              tagCounts=combined)

        # Update MediaTags for added tags
        if operation == 1:
            db.update_media_tags(
                file_id, f.get("fileType"), f.get("fileUrl"),
                f.get("thumbnailUrl", ""),
                {tag: manual_tags[tag] for tag in tags},
            )
            # Notify subscribers for newly added tags
            for tag in tags:
                try:
                    sns_utils.publish_tag_notification(
                        tag, f.get("fileUrl"),
                        f.get("thumbnailUrl", ""),
                        manual_tags[tag],
                    )
                except Exception as e:
                    logger.error(f"Failed to notify for tag '{tag}': {e}")

        results.append({"fileId": file_id, "fileUrl": f.get("fileUrl"), "status": "updated"})

    return _ok({"updated": results})


def handle_delete_files(event: dict) -> dict:
    """POST /v1/files/delete — Delete files from S3 and DynamoDB."""
    body = _parse_body(event)
    urls = body.get("urls", [])

    if not urls:
        return _err("Missing urls list")

    files = db.query_files_by_urls(urls)
    results = []

    for f in files:
        file_id = f["fileId"]
        object_key = f.get("objectKey", "")
        thumbnail_key = f.get("thumbnailKey", "")

        # Delete from S3
        if object_key:
            s3_utils.delete_s3_object(object_key)
        if thumbnail_key:
            s3_utils.delete_s3_object(thumbnail_key)

        # Delete video frames
        file_type = f.get("fileType", "image")
        if file_type == "video":
            s3_utils.delete_s3_prefix(f"frames/{file_id}/")
            s3_utils.delete_s3_prefix(f"thumbnails/frames/{file_id}/")

        # Remove MediaTags entries
        db.remove_all_media_tags(file_id)

        # Mark file as deleted (soft delete)
        db.mark_file_deleted(file_id)

        results.append({"fileId": file_id, "fileUrl": f.get("fileUrl"), "status": "deleted"})

    return _ok({"deleted": results})


def handle_create_subscription(event: dict) -> dict:
    """POST /v1/notifications/subscriptions"""
    owner_sub, email = _get_user(event)
    body = _parse_body(event)
    tags = body.get("tags", [])

    if not tags or not email:
        return _err("Missing tags or email")

    # Subscribe to SNS for each tag
    arns = []
    for tag in tags:
        try:
            arn = sns_utils.create_email_subscription(email, tag)
            arns.append({"tag": tag, "subscriptionArn": arn})
        except Exception as e:
            logger.error(f"Failed to subscribe {email} to {tag}: {e}")

    if not arns:
        return _err("Failed to create any subscriptions", 500)

    sub = db.create_subscription(owner_sub, email, tags, arns)
    return _ok(sub, 201)


def handle_list_subscriptions(event: dict) -> dict:
    """GET /v1/notifications/subscriptions"""
    owner_sub, _ = _get_user(event)
    subs = db.get_subscriptions_by_owner(owner_sub)
    return _ok({"subscriptions": subs})


def handle_delete_subscription(event: dict) -> dict:
    """DELETE /v1/notifications/subscriptions/{subscriptionId}"""
    sub_id = event.get("pathParameters", {}).get("subscriptionId", "")

    sub = db.get_subscription(sub_id)
    if not sub:
        return _err("Subscription not found", 404)

    # Unsubscribe from SNS
    for arn_item in sub.get("snsSubscriptionArns", []):
        arn = arn_item.get("subscriptionArn", "")
        if arn and arn != "pending confirmation":
            try:
                sns_utils.unsubscribe(arn)
            except Exception as e:
                logger.error(f"Failed to unsubscribe {arn}: {e}")

    db.delete_subscription(sub_id)
    return _ok({"status": "deleted", "subscriptionId": sub_id})


# ==================== Router ====================

ROUTES = {
    "POST /v1/uploads/init": handle_upload_init,
    "POST /v1/uploads/complete": handle_upload_complete,
    "GET /v1/files/{fileId}": handle_get_file,
    "POST /v1/query/tags": handle_query_tags,
    "POST /v1/query/species": handle_query_species,
    "POST /v1/query/thumbnail": handle_query_thumbnail,
    "POST /v1/tags/bulk": handle_bulk_tags,
    "POST /v1/files/delete": handle_delete_files,
    "POST /v1/notifications/subscriptions": handle_create_subscription,
    "GET /v1/notifications/subscriptions": handle_list_subscriptions,
    "DELETE /v1/notifications/subscriptions/{subscriptionId}": handle_delete_subscription,
}


def lambda_handler(event: dict, context) -> dict:
    logger.info(f"Event: {json.dumps(event, default=str)[:2000]}")

    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return _ok({})

    route = _route_key(event)
    handler = ROUTES.get(route)

    if not handler:
        return _err(f"Not found: {route}", 404)

    try:
        return handler(event)
    except Exception as e:
        logger.error(f"Handler error [{route}]: {traceback.format_exc()}")
        return _err(str(e), 500)
