"""
DynamoDB operations for AussieEcoLens.

Tables:
  - Files:   PK=fileId, GSI=ownerSub-checksum-index, fileUrl-index, thumbnailUrl-index, ownerSub-index
  - MediaTags: PK=tagName, SK=fileId
  - TagSubscriptions: PK=subscriptionId, GSI=ownerSub-index, tagName-index
"""
import os
import uuid
import time
import logging
from typing import Optional
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger(__name__)

FILES_TABLE = os.getenv("FILES_TABLE", "AussieEcoLens-Files")
MEDIA_TAGS_TABLE = os.getenv("MEDIA_TAGS_TABLE", "AussieEcoLens-MediaTags")
TAG_SUBSCRIPTIONS_TABLE = os.getenv("TAG_SUBS_TABLE", "AussieEcoLens-TagSubscriptions")

dynamodb = boto3.resource("dynamodb")
files_tbl = dynamodb.Table(FILES_TABLE)
tags_tbl = dynamodb.Table(MEDIA_TAGS_TABLE)
subs_tbl = dynamodb.Table(TAG_SUBSCRIPTIONS_TABLE)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_id() -> str:
    return str(uuid.uuid4())


# ==================== Files Table ====================

def create_file_record(
    file_id: str,
    owner_sub: str,
    owner_email: str,
    original_filename: str,
    file_type: str,
    content_type: str,
    size_bytes: int,
    checksum_sha256: str,
    bucket: str,
    object_key: str,
    file_url: str,
    status: str = "pending",
) -> dict:
    now = _now_iso()
    item = {
        "fileId": file_id,
        "ownerSub": owner_sub,
        "ownerEmail": owner_email,
        "originalFilename": original_filename,
        "fileType": file_type,
        "contentType": content_type,
        "sizeBytes": size_bytes,
        "checksumSha256": checksum_sha256,
        "status": status,
        "bucket": bucket,
        "objectKey": object_key,
        "fileUrl": file_url,
        "createdAt": now,
        "updatedAt": now,
    }
    files_tbl.put_item(Item=item)
    return item


def get_file(file_id: str) -> Optional[dict]:
    resp = files_tbl.get_item(Key={"fileId": file_id})
    return resp.get("Item")


def update_file_status(file_id: str, status: str, **extra_fields):
    now = _now_iso()
    expr = "SET #s = :s, updatedAt = :now"
    names = {"#s": "status"}
    values = {":s": status, ":now": now}

    for idx, (k, v) in enumerate(extra_fields.items()):
        if v is None:
            continue  # skip None values (GSI keys reject empty/null)
        key = f"#k{idx}"
        val = f":v{idx}"
        expr += f", {key} = {val}"
        names[key] = k
        values[val] = v

    files_tbl.update_item(
        Key={"fileId": file_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def check_duplicate(owner_sub: str, checksum_sha256: str) -> Optional[dict]:
    """Check if user already owns a file with the same checksum."""
    resp = files_tbl.query(
        IndexName="ownerSub-checksum-index",
        KeyConditionExpression=Key("ownerSub").eq(owner_sub) & Key("checksumSha256").eq(checksum_sha256),
        FilterExpression="attribute_not_exists(deletedAt)",
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def query_files_by_urls(urls: list) -> list:
    """Batch get files by fileUrl using the fileUrl-index GSI."""
    files = []
    for url in urls:
        resp = files_tbl.query(
            IndexName="fileUrl-index",
            KeyConditionExpression=Key("fileUrl").eq(url),
            Limit=1,
        )
        items = resp.get("Items", [])
        if items:
            files.append(items[0])
    return files


def find_file_by_thumbnail(thumbnail_url: str) -> Optional[dict]:
    resp = files_tbl.query(
        IndexName="thumbnailUrl-index",
        KeyConditionExpression=Key("thumbnailUrl").eq(thumbnail_url),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def mark_file_deleted(file_id: str):
    now = _now_iso()
    files_tbl.update_item(
        Key={"fileId": file_id},
        UpdateExpression="SET deletedAt = :now, #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":now": now, ":s": "deleted"},
    )


# ==================== MediaTags Table ====================

def update_media_tags(file_id: str, file_type: str, file_url: str,
                      thumbnail_url: str, tag_counts: dict):
    """For each tag, put/update a MediaTags record."""
    now = _now_iso()
    for tag_name, count in tag_counts.items():
        tags_tbl.put_item(Item={
            "tagName": tag_name.lower(),
            "fileId": file_id,
            "count": count,
            "fileType": file_type,
            "fileUrl": file_url,
            "thumbnailUrl": thumbnail_url,
            "updatedAt": now,
        })


def remove_media_tags(file_id: str, tag_names: list):
    """Remove specific tags for a file."""
    for tag in tag_names:
        tags_tbl.delete_item(
            Key={"tagName": tag.lower(), "fileId": file_id},
        )


def remove_all_media_tags(file_id: str):
    """Remove all MediaTags entries for a file (used on file delete).
    Since we don't have a GSI on fileId alone, we query by iterating
    known tags from the file record, or use a scan (small dataset).
    In production: add a GSI on fileId.
    """
    # Scan approach — acceptable for typical assignment data volume
    scan = tags_tbl.scan(
        FilterExpression=Attr("fileId").eq(file_id),
    )
    with tags_tbl.batch_writer() as batch:
        for item in scan.get("Items", []):
            batch.delete_item(
                Key={"tagName": item["tagName"], "fileId": item["fileId"]}
            )


def query_files_by_tags(tag_filters: dict) -> list:
    """
    Multi-tag AND query with minimum counts.

    tag_filters: {"kangaroo": 3, "wombat": 2}
    → files where kangaroo count >= 3 AND wombat count >= 2.

    Algorithm:
      1. For each tag, query MediaTags table
      2. Filter by minimum count
      3. Intersect fileId sets
      4. Batch-get file records from Files table
    """
    if not tag_filters:
        return []

    file_id_sets = []
    for tag_name, min_count in tag_filters.items():
        resp = tags_tbl.query(
            KeyConditionExpression=Key("tagName").eq(tag_name.lower()),
        )
        matching = set()
        for item in resp.get("Items", []):
            if int(item.get("count", 0)) >= min_count:
                matching.add(item["fileId"])
        # Handle pagination
        while "LastEvaluatedKey" in resp:
            resp = tags_tbl.query(
                KeyConditionExpression=Key("tagName").eq(tag_name.lower()),
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            for item in resp.get("Items", []):
                if int(item.get("count", 0)) >= min_count:
                    matching.add(item["fileId"])
        file_id_sets.append(matching)

    # Intersection (AND logic)
    if not file_id_sets:
        return []
    common_ids = file_id_sets[0]
    for s in file_id_sets[1:]:
        common_ids = common_ids & s

    if not common_ids:
        return []

    # Batch-get file records (DynamoDB batch_get_item max 100 per call)
    files = []
    file_ids = list(common_ids)
    for i in range(0, len(file_ids), 100):
        batch = file_ids[i:i + 100]
        keys = [{"fileId": fid} for fid in batch]
        # Use batch get
        resp = dynamodb.batch_get_item(
            RequestItems={FILES_TABLE: {"Keys": keys}}
        )
        for item in resp.get("Responses", {}).get(FILES_TABLE, []):
            if "deletedAt" not in item:
                # Flatten Decimal → int for JSON
                item = _decimal_to_int(item)
                files.append(item)

    return files


def query_files_by_species(species_list: list) -> list:
    """Species query: at least 1 of each species (min count = 1)."""
    filters = {s: 1 for s in species_list}
    return query_files_by_tags(filters)


# ==================== TagSubscriptions Table ====================

def create_subscription(owner_sub: str, email: str, tags: list,
                        sns_sub_arns: list) -> dict:
    now = _now_iso()
    sub_id = _new_id()
    item = {
        "subscriptionId": sub_id,
        "ownerSub": owner_sub,
        "email": email,
        "tags": tags,
        "snsSubscriptionArns": sns_sub_arns,
        "status": "active",
        "createdAt": now,
    }
    subs_tbl.put_item(Item=item)
    return item


def get_subscriptions_by_owner(owner_sub: str) -> list:
    resp = subs_tbl.query(
        IndexName="ownerSub-index",
        KeyConditionExpression=Key("ownerSub").eq(owner_sub),
    )
    return resp.get("Items", [])


def get_subscription(sub_id: str) -> Optional[dict]:
    resp = subs_tbl.get_item(Key={"subscriptionId": sub_id})
    return resp.get("Item")


def delete_subscription(sub_id: str):
    subs_tbl.delete_item(Key={"subscriptionId": sub_id})


def find_subscriptions_by_tag(tag_name: str) -> list:
    """Find all active subscriptions watching a specific tag."""
    resp = subs_tbl.query(
        IndexName="tagName-index",
        KeyConditionExpression=Key("tagName").eq(tag_name.lower()),
        FilterExpression=Attr("status").eq("active"),
    )
    return resp.get("Items", [])


# ==================== Helpers ====================

def _decimal_to_int(item: dict) -> dict:
    """DynamoDB returns numbers as Decimal; convert to int/float for JSON."""
    out = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            out[k] = int(v) if v % 1 == 0 else float(v)
        elif isinstance(v, dict):
            out[k] = _decimal_to_int(v)
        elif isinstance(v, list):
            out[k] = [
                _decimal_to_int(i) if isinstance(i, dict) else
                int(i) if isinstance(i, Decimal) and i % 1 == 0 else
                float(i) if isinstance(i, Decimal) else i
                for i in v
            ]
        else:
            out[k] = v
    return out
