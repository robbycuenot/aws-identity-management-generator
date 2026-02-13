"""
TFC Agent Lifecycle Manager

Manages ECS Fargate agents for Terraform Cloud runs with:
- Long-running agents that handle multiple jobs
- Auto-scaling based on pending work
- Auto-shutdown after idle timeout
- DynamoDB state tracking for coordination
- GitHub webhook support for speculative plans
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
GITHUB_WEBHOOK_SECRET = os.environ.get('GITHUB_WEBHOOK_SECRET', '')
TABLE_NAME = os.environ['TABLE_NAME']
MAX_AGENTS = int(os.environ.get('MAX_AGENTS', '3'))
IDLE_TIMEOUT_MINUTES = int(os.environ.get('IDLE_TIMEOUT_MINUTES', '15'))

# AWS clients
ecs = boto3.client('ecs')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)


def verify_tfc_signature(payload: bytes, signature: str) -> bool:
    """Verify TFC webhook HMAC-SHA512 signature."""
    if not signature:
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_github_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature or not GITHUB_WEBHOOK_SECRET:
        return False
    # GitHub signature format: sha256=<hex>
    if not signature.startswith('sha256='):
        return False
    expected = 'sha256=' + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
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


def record_github_event(pr_number: int, action: str, repo: str):
    """Record a GitHub PR event in DynamoDB for tracking."""
    now = datetime.now(timezone.utc).isoformat()
    table.put_item(Item={
        'pk': f'GITHUB_PR#{repo}#{pr_number}',
        'sk': f'EVENT#{action}#{now}',
        'entity_type': 'github_event',
        'pr_number': pr_number,
        'action': action,
        'repository': repo,
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
    
    # Events that indicate work needs an agent
    work_events = ['run:created', 'run:planning', 'run:applying', 'github:pull_request']
    
    # Always ensure at least one agent for work-producing events
    if event_type in work_events and active_agents == 0:
        return True
    
    # For new work signals, scale up if under max
    # run:applying is included because a confirmed apply after a long idle gap
    # (e.g. 2 hours) means all agents were stopped by the idle checker
    if event_type in ['run:created', 'run:planning', 'run:applying', 'github:pull_request'] and active_agents < MAX_AGENTS:
        return True
    
    return False


def handle_tfc_webhook(event_type: str, run_id: str, workspace: str):
    """Handle incoming TFC webhook event."""
    print(f"Handling TFC {event_type} for run {run_id} in {workspace}")
    
    # Record the event
    record_run_event(run_id, event_type, workspace)
    
    # Update activity on existing agents (keeps them alive)
    update_agent_activity()
    
    if event_type in ['run:created', 'run:planning', 'run:applying', 'run:needs_attention']:
        # These events indicate work - ensure we have agents
        if should_scale_up(event_type):
            start_agent()
        else:
            print(f"Sufficient agents running, not scaling up")
    
    elif event_type in ['run:completed', 'run:errored']:
        # Run finished - agents will self-terminate after idle timeout
        # No action needed, just recorded the event
        print(f"Run {run_id} finished with {event_type}")


def handle_github_webhook(action: str, pr_number: int, repo: str, base_ref: str):
    """Handle incoming GitHub pull_request webhook event."""
    print(f"Handling GitHub PR #{pr_number} action={action} repo={repo} base={base_ref}")
    
    # Only trigger on PRs targeting main/master
    if base_ref not in ['main', 'master']:
        print(f"Ignoring PR targeting {base_ref} (not main/master)")
        return
    
    # Only trigger on actions that indicate new work
    # opened: new PR created
    # synchronize: new commits pushed to PR
    # reopened: PR was closed and reopened
    if action not in ['opened', 'synchronize', 'reopened']:
        print(f"Ignoring PR action {action}")
        return
    
    # Record the event
    record_github_event(pr_number, action, repo)
    
    # Update activity on existing agents
    update_agent_activity()
    
    # Scale up for speculative plan
    if should_scale_up('github:pull_request'):
        start_agent()
    else:
        print(f"Sufficient agents running, not scaling up")


def handler(event, context):
    """Lambda handler for API Gateway webhook."""
    print(f"Received event: {json.dumps(event)}")
    
    # Extract payload and headers
    body = event.get('body', '')
    if event.get('isBase64Encoded'):
        import base64
        body = base64.b64decode(body).decode('utf-8')
    
    headers = {k.lower(): v for k, v in event.get('headers', {}).items()}
    
    # Parse payload first to check for verification request
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON'})
        }
    
    # Determine webhook source by headers
    tfc_signature = headers.get('x-tfe-notification-signature', '')
    github_signature = headers.get('x-hub-signature-256', '')
    github_event = headers.get('x-github-event', '')
    
    # Handle TFC verification request BEFORE signature check
    if payload.get('payload_version') == 1 and 'verification' in str(payload):
        print("TFC verification request - responding OK")
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'ok'})
        }
    
    # Handle GitHub ping event (sent when webhook is created)
    if github_event == 'ping':
        print("GitHub ping event - responding OK")
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'ok', 'message': 'pong'})
        }
    
    # Route based on webhook source
    if github_signature and github_event:
        # GitHub webhook
        if not verify_github_signature(body.encode(), github_signature):
            print("Invalid GitHub signature")
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Invalid signature'})
            }
        
        if github_event != 'pull_request':
            print(f"Ignoring GitHub event type: {github_event}")
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'ignored', 'event': github_event})
            }
        
        # Extract PR info
        action = payload.get('action', 'unknown')
        pr = payload.get('pull_request', {})
        pr_number = payload.get('number', 0)
        repo = payload.get('repository', {}).get('full_name', 'unknown')
        base_ref = pr.get('base', {}).get('ref', 'unknown')
        
        try:
            handle_github_webhook(action, pr_number, repo, base_ref)
        except Exception as e:
            print(f"Error handling GitHub webhook: {e}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'ok',
                'source': 'github',
                'active_agents': get_active_agent_count()
            })
        }
    
    elif tfc_signature:
        # TFC webhook
        if not verify_tfc_signature(body.encode(), tfc_signature):
            print("Invalid TFC signature")
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Invalid signature'})
            }
        
        # Extract run info - run_id and workspace_name are top-level fields,
        # while trigger is inside each notification object
        run_id = payload.get('run_id', 'unknown')
        workspace = payload.get('workspace_name', 'unknown')
        
        notifications = payload.get('notifications', [])
        if not notifications:
            print(f"No notifications in payload for run {run_id} in {workspace}")
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'no notifications'})
            }
        
        for notification in notifications:
            event_type = notification.get('trigger', 'unknown')
            
            try:
                handle_tfc_webhook(event_type, run_id, workspace)
            except Exception as e:
                print(f"Error handling TFC webhook: {e}")
                continue
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'ok',
                'source': 'tfc',
                'active_agents': get_active_agent_count()
            })
        }
    
    else:
        print("Unknown webhook source - no valid signature header found")
        return {
            'statusCode': 401,
            'body': json.dumps({'error': 'Unknown webhook source'})
        }
