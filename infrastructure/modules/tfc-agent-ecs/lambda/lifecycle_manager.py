"""
TFC Agent Lifecycle Manager

Manages ECS Fargate agents for Terraform Cloud runs with:
- Long-running agents that handle multiple jobs
- Auto-scaling based on pending work
- Auto-shutdown after idle timeout
- DynamoDB state tracking for coordination
"""

import json
import os
import time
import hmac
import hashlib
import boto3
from datetime import datetime, timezone
from decimal import Decimal

# Environment variables
CLUSTER_ARN = os.environ['CLUSTER_ARN']
TASK_DEFINITION = os.environ['TASK_DEFINITION']
SUBNETS = os.environ['SUBNETS'].split(',')
SECURITY_GROUP = os.environ['SECURITY_GROUP']
WEBHOOK_SECRET = os.environ['WEBHOOK_SECRET']
TABLE_NAME = os.environ['TABLE_NAME']
MAX_AGENTS = int(os.environ.get('MAX_AGENTS', '3'))
IDLE_TIMEOUT_MINUTES = int(os.environ.get('IDLE_TIMEOUT_MINUTES', '15'))

# AWS clients
ecs = boto3.client('ecs')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify TFC webhook HMAC signature."""
    if not signature:
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def get_running_agents() -> list:
    """Get list of currently running agent task ARNs from DynamoDB."""
    try:
        response = table.scan(
            FilterExpression='entity_type = :type AND #s = :status',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':type': 'agent',
                ':status': 'running'
            }
        )
        return response.get('Items', [])
    except Exception as e:
        print(f"Error scanning agents: {e}")
        return []


def verify_agent_running(task_arn: str) -> bool:
    """Check if an ECS task is actually still running."""
    try:
        response = ecs.describe_tasks(
            cluster=CLUSTER_ARN,
            tasks=[task_arn]
        )
        if response['tasks']:
            task = response['tasks'][0]
            return task['lastStatus'] in ['RUNNING', 'PENDING', 'PROVISIONING']
        return False
    except Exception as e:
        print(f"Error checking task {task_arn}: {e}")
        return False


def cleanup_stale_agents():
    """Remove DynamoDB records for agents that are no longer running."""
    agents = get_running_agents()
    for agent in agents:
        task_arn = agent['task_arn']
        if not verify_agent_running(task_arn):
            print(f"Cleaning up stale agent record: {task_arn}")
            try:
                table.delete_item(Key={'pk': agent['pk'], 'sk': agent['sk']})
            except Exception as e:
                print(f"Error deleting stale record: {e}")


def get_active_agent_count() -> int:
    """Get count of actually running agents (verified with ECS)."""
    cleanup_stale_agents()
    return len(get_running_agents())


def start_agent() -> str:
    """Start a new ECS Fargate agent task."""
    response = ecs.run_task(
        cluster=CLUSTER_ARN,
        taskDefinition=TASK_DEFINITION,
        launchType='FARGATE',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': SUBNETS,
                'securityGroups': [SECURITY_GROUP],
                'assignPublicIp': 'DISABLED'
            }
        },
        count=1
    )
    
    if response['tasks']:
        task_arn = response['tasks'][0]['taskArn']
        task_id = task_arn.split('/')[-1]
        
        # Record in DynamoDB
        now = datetime.now(timezone.utc).isoformat()
        table.put_item(Item={
            'pk': f'AGENT#{task_id}',
            'sk': 'METADATA',
            'entity_type': 'agent',
            'task_arn': task_arn,
            'status': 'running',
            'started_at': now,
            'last_activity': now,
            'ttl': int(time.time()) + (24 * 60 * 60)  # 24 hour TTL for cleanup
        })
        
        print(f"Started agent: {task_arn}")
        return task_arn
    else:
        failures = response.get('failures', [])
        print(f"Failed to start agent: {failures}")
        raise Exception(f"Failed to start ECS task: {failures}")


def record_run_event(run_id: str, event_type: str, workspace: str):
    """Record a run event in DynamoDB for tracking."""
    now = datetime.now(timezone.utc).isoformat()
    table.put_item(Item={
        'pk': f'RUN#{run_id}',
        'sk': f'EVENT#{event_type}#{now}',
        'entity_type': 'run_event',
        'run_id': run_id,
        'event_type': event_type,
        'workspace': workspace,
        'timestamp': now,
        'ttl': int(time.time()) + (7 * 24 * 60 * 60)  # 7 day TTL
    })


def update_agent_activity():
    """Update last_activity timestamp for all running agents."""
    agents = get_running_agents()
    now = datetime.now(timezone.utc).isoformat()
    for agent in agents:
        try:
            table.update_item(
                Key={'pk': agent['pk'], 'sk': agent['sk']},
                UpdateExpression='SET last_activity = :now',
                ExpressionAttributeValues={':now': now}
            )
        except Exception as e:
            print(f"Error updating agent activity: {e}")


def should_scale_up(event_type: str) -> bool:
    """Determine if we should start a new agent based on current state."""
    active_agents = get_active_agent_count()
    
    # Always ensure at least one agent for work-producing events
    if event_type in ['run:created', 'run:applying'] and active_agents == 0:
        return True
    
    # For run:created, scale up if under max (new work coming)
    if event_type == 'run:created' and active_agents < MAX_AGENTS:
        # Simple heuristic: if we have pending work signals, add capacity
        # In practice, TFC agent pool handles job distribution
        return True
    
    return False


def handle_webhook(event_type: str, run_id: str, workspace: str):
    """Handle incoming TFC webhook event."""
    print(f"Handling {event_type} for run {run_id} in {workspace}")
    
    # Record the event
    record_run_event(run_id, event_type, workspace)
    
    # Update activity on existing agents (keeps them alive)
    update_agent_activity()
    
    if event_type in ['run:created', 'run:applying', 'run:needs_attention']:
        # These events indicate work - ensure we have agents
        if should_scale_up(event_type):
            start_agent()
        else:
            print(f"Sufficient agents running, not scaling up")
    
    elif event_type in ['run:completed', 'run:errored']:
        # Run finished - agents will self-terminate after idle timeout
        # No action needed, just recorded the event
        print(f"Run {run_id} finished with {event_type}")


def handler(event, context):
    """Lambda handler for API Gateway webhook."""
    print(f"Received event: {json.dumps(event)}")
    
    # Extract payload and signature
    body = event.get('body', '')
    if event.get('isBase64Encoded'):
        import base64
        body = base64.b64decode(body).decode('utf-8')
    
    headers = {k.lower(): v for k, v in event.get('headers', {}).items()}
    signature = headers.get('x-tfe-notification-signature', '')
    
    # Parse payload first to check for verification request
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON'})
        }
    
    # Handle verification request BEFORE signature check
    # TFC sends this when creating/updating notification configuration
    if payload.get('payload_version') == 1 and 'verification' in str(payload):
        print("Verification request - responding OK")
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'ok'})
        }
    
    # Verify signature for all other requests
    if not verify_signature(body.encode(), signature):
        print("Invalid signature")
        return {
            'statusCode': 401,
            'body': json.dumps({'error': 'Invalid signature'})
        }
    
    # Extract run info
    notifications = payload.get('notifications', [])
    if not notifications:
        print("No notifications in payload")
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'no notifications'})
        }
    
    for notification in notifications:
        run_id = notification.get('run_id', 'unknown')
        event_type = notification.get('trigger', 'unknown')
        workspace = notification.get('workspace_name', 'unknown')
        
        try:
            handle_webhook(event_type, run_id, workspace)
        except Exception as e:
            print(f"Error handling webhook: {e}")
            # Don't fail the whole request - TFC will retry
            continue
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'status': 'ok',
            'active_agents': get_active_agent_count()
        })
    }
