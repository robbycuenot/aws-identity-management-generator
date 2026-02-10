"""
TFC Agent Webhook Handler

Receives webhook notifications from Terraform Cloud and starts ECS tasks
to process runs. Uses single-execution mode so tasks exit after one job.
"""

import hashlib
import hmac
import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ecs = boto3.client("ecs")

# Environment variables
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
TASK_DEFINITION = os.environ["TASK_DEFINITION"]
SUBNETS = os.environ["SUBNETS"].split(",")
SECURITY_GROUP = os.environ["SECURITY_GROUP"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
TASKS_PER_RUN = int(os.environ.get("TASKS_PER_RUN", "2"))


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify HMAC-SHA512 signature from TFC."""
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def start_ecs_tasks(run_id: str, workspace_name: str) -> dict:
    """Start ECS tasks to process the run."""
    logger.info(f"Starting {TASKS_PER_RUN} ECS tasks for run {run_id} in workspace {workspace_name}")
    
    response = ecs.run_task(
        cluster=CLUSTER_ARN,
        taskDefinition=TASK_DEFINITION,
        count=TASKS_PER_RUN,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": SUBNETS,
                "securityGroups": [SECURITY_GROUP],
                "assignPublicIp": "DISABLED"
            }
        },
        startedBy=f"tfc-webhook/{run_id[:8]}"
    )
    
    started = len(response.get("tasks", []))
    failures = response.get("failures", [])
    
    if failures:
        logger.error(f"Failed to start some tasks: {failures}")
    
    logger.info(f"Started {started} tasks for run {run_id}")
    return {"started": started, "failures": len(failures)}


def handler(event, context):
    """Lambda handler for TFC webhook notifications."""
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Get signature from headers
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    signature = headers.get("x-tfe-notification-signature", "")
    
    # Get and verify payload
    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body).decode("utf-8")
    
    if not verify_signature(body.encode("utf-8"), signature):
        logger.warning("Invalid signature")
        return {"statusCode": 401, "body": "Invalid signature"}
    
    # Parse notification
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload")
        return {"statusCode": 400, "body": "Invalid JSON"}
    
    # Extract notification details
    notifications = payload.get("notifications", [])
    if not notifications:
        logger.info("No notifications in payload")
        return {"statusCode": 200, "body": "OK"}
    
    notification = notifications[0]
    trigger = notification.get("trigger")
    run_id = notification.get("run_id", "unknown")
    workspace_name = notification.get("workspace_name", "unknown")
    
    logger.info(f"Notification: trigger={trigger}, run_id={run_id}, workspace={workspace_name}")
    
    # Start tasks for:
    # - run:created: New runs needing agents for plan
    # - run:needs_attention: Runs ready for apply after approval
    if trigger in ("run:created", "run:needs_attention"):
        result = start_ecs_tasks(run_id, workspace_name)
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Tasks started", "trigger": trigger, **result})
        }
    
    logger.info(f"Ignoring trigger: {trigger}")
    return {"statusCode": 200, "body": "OK"}
