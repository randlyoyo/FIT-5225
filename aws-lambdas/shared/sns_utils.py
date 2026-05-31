"""
SNS notification utilities.
Single SNS topic with message-attribute-based filter policies.
"""
import os
import json
import logging

import boto3

logger = logging.getLogger(__name__)

SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")

sns = boto3.client("sns")


def create_email_subscription(email: str, tag_name: str) -> str:
    """
    Subscribe an email to tag notifications via SNS.
    Returns the subscription ARN (pending confirmation).
    Filter policy is set to only deliver messages for the specific tag.
    """
    resp = sns.subscribe(
        TopicArn=SNS_TOPIC_ARN,
        Protocol="email",
        Endpoint=email,
        Attributes={
            "FilterPolicy": json.dumps({
                "tag": [tag_name.lower()],
            }),
        },
        ReturnSubscriptionArn=True,
    )
    return resp["SubscriptionArn"]


def unsubscribe(subscription_arn: str):
    """Unsubscribe from SNS topic."""
    sns.unsubscribe(SubscriptionArn=subscription_arn)


def publish_tag_notification(tag_name: str, file_url: str,
                             thumbnail_url: str, count: int):
    """
    Publish a notification when a new file with a watched tag is added.
    """
    if not SNS_TOPIC_ARN:
        logger.warning("SNS_TOPIC_ARN not configured; skipping notification")
        return

    message = json.dumps({
        "tag": tag_name,
        "fileUrl": file_url,
        "thumbnailUrl": thumbnail_url,
        "count": count,
        "message": (
            f"A new file tagged '{tag_name}' has been added to AussieEcoLens.\n"
            f"View: {file_url}"
        ),
    })

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=message,
        Subject=f"[AussieEcoLens] New '{tag_name}' sighting!",
        MessageAttributes={
            "tag": {
                "DataType": "String",
                "StringValue": tag_name.lower(),
            },
        },
    )
