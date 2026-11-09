"""
TFC Agent Lifecycle Manager

Manages ECS Fargate agents for Terraform Cloud runs with:
- Long-running agents that handle multiple jobs
- Auto-scaling based on pending work
- Auto-shutdown after idle timeout
- DynamoDB state tracking for coordination
- GitHub webhook support for speculative plans
- Pre-apply run task support for confirmed applies
"""

import json
import os
import time
import hmac
import hashlib
import uuid
import urllib.request
import urllib.error
import boto3
from datetime import datetime, timezone

# Environment variables
CLUSTER_ARN = os.environ['CLUSTER_ARN']
TASK_DEFINITION = os.environ['TASK_DEFINITION']
SUBNETS = os.environ['SUBNETS'].split(',')
SECURITY_GROUP = os.environ['SECURITY_GROUP']
WEBHOOK_SECRET = os.environ['WEBHOOK_SECRET']
GITHUB_WEBHOOK_SECRET = os.environ.get('GITHUB_WEBHOOK_SECRET', '')
RUN_TASK_HMAC_KEY = os.environ.get('RUN_TASK_HMAC_KEY', '')
TABLE_NAME = os.environ['TABLE_NAME']
MAX_AGENTS = int(os.environ.get('MAX_AGENTS', '3'))
IDLE_TIMEOUT_MINUTES = int(os.environ.get('IDLE_TIMEOUT_MINUTES', '15'))
AGENT_NAME_PREFIX = os.environ.get('AGENT_NAME_PREFIX', 'ecs-agent')
TFC_ADDRESS = os.environ.get('TFC_ADDRESS', 'app.terraform.io')

# AWS clients
ecs = boto3.client('ecs')
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)


def http_response(status_code: int, body: dict) -> dict:
    return {'statusCode': status_code, 'body': json.dumps(body)}


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


def verify_run_task_signature(payload: bytes, signature: str) -> bool:
    """Verify TFC run task HMAC-SHA512 signature."""
    if not signature or not RUN_TASK_HMAC_KEY:
        return False
    expected = hmac.new(
        RUN_TASK_HMAC_KEY.encode(),
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
    # Unique name lets the idle checker match this task to its TFC agent status
    agent_name = f"{AGENT_NAME_PREFIX}-{uuid.uuid4().hex[:8]}"
    run_response = ecs.run_task(
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
        overrides={
            'containerOverrides': [{
                'name': 'tfc-agent',
                'environment': [{'name': 'TFC_AGENT_NAME', 'value': agent_name}]
            }]
        },
        count=1
    )
    
    if run_response['tasks']:
        task_arn = run_response['tasks'][0]['taskArn']
        task_id = task_arn.split('/')[-1]
        
        # Record in DynamoDB
        now = datetime.now(timezone.utc).isoformat()
        table.put_item(Item={
            'pk': f'AGENT#{task_id}',
            'sk': 'METADATA',
            'entity_type': 'agent',
            'task_arn': task_arn,
            'agent_name': agent_name,
            'status': 'running',
            'started_at': now,
            'last_activity': now,
            'ttl': int(time.time()) + (24 * 60 * 60)  # 24 hour TTL for cleanup
        })
        
        print(f"Started agent: {task_arn} ({agent_name})")
        return task_arn
    else:
        failures = run_response.get('failures', [])
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


def send_run_task_result(callback_url: str, access_token: str, status: str, message: str):
    """Report the run task result back to TFC."""
    result = {
        'data': {
            'type': 'task-results',
            'attributes': {'status': status, 'message': message}
        }
    }
    request = urllib.request.Request(
        callback_url,
        data=json.dumps(result).encode(),
        method='PATCH',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/vnd.api+json'
        }
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as callback_response:
            print(f"Run task callback returned {callback_response.status}")
    except urllib.error.HTTPError as e:
        print(f"Run task callback failed with HTTP {e.code}: {e.read()[:500]}")
    except Exception as e:
        print(f"Run task callback failed: {e}")


def process_run_task(job: dict):
    """Ensure an agent is available for a confirmed apply, then report back to TFC."""
    run_id = job.get('run_id', 'unknown')
    workspace = job.get('workspace_name', 'unknown')
    stage = job.get('stage')
    print(f"Processing run task stage={stage} for run {run_id} in {workspace}")

    status = 'passed'
    if stage == 'pre_apply' and not job.get('is_speculative'):
        try:
            record_run_event(run_id, 'run_task:pre_apply', workspace)
            update_agent_activity()
            if get_active_agent_count() == 0:
                start_agent()
                message = 'Started a TFC agent for this apply'
            else:
                message = 'TFC agent already running'
        except Exception as e:
            print(f"Error ensuring agent for run {run_id}: {e}")
            status = 'failed'
            message = 'Could not start a TFC agent; check the lifecycle Lambda logs'
    else:
        message = f'No action needed for stage {stage}'

    print(f"Run task result for {run_id}: {status} - {message}")
    send_run_task_result(job['callback_url'], job['access_token'], status, message)


def handle_run_task_request(body: str, signature: str, context) -> dict:
    """Acknowledge a TFC run task request and hand the work to an async invocation."""
    if not verify_run_task_signature(body.encode(), signature):
        print("Invalid run task signature")
        return http_response(401, {'error': 'Invalid signature'})

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as e:
        print(f"Invalid run task JSON: {e}")
        return http_response(400, {'error': 'Invalid JSON'})

    callback_url = payload.get('task_result_callback_url') or ''
    access_token = payload.get('access_token') or ''
    stage = payload.get('stage')
    run_id = payload.get('run_id')

    # The endpoint test sent when the run task is created only needs a 200
    if not callback_url or not access_token:
        print(f"Run task request without callback (stage={stage}, run={run_id}) - responding OK")
        return http_response(200, {'status': 'ok'})

    if not callback_url.startswith(f'https://{TFC_ADDRESS}/api/v2/task-results/'):
        print(f"Rejecting run task callback URL outside {TFC_ADDRESS}")
        return http_response(400, {'error': 'Unexpected callback URL'})

    job = {
        'callback_url': callback_url,
        'access_token': access_token,
        'stage': stage,
        'run_id': run_id,
        'workspace_name': payload.get('workspace_name'),
        'is_speculative': bool(payload.get('is_speculative')),
    }
    # TFC requires the 200 before the result callback, so finish the work asynchronously
    try:
        lambda_client.invoke(
            FunctionName=context.invoked_function_arn,
            InvocationType='Event',
            Payload=json.dumps({'run_task_callback': job}).encode()
        )
    except Exception as e:
        print(f"Failed to queue run task processing for {run_id}: {e}")
        return http_response(500, {'error': 'Failed to queue run task'})

    print(f"Accepted run task stage={stage} for run {run_id}")
    return http_response(200, {'status': 'accepted'})


def handler(event, context):
    """Lambda handler for API Gateway webhook."""
    # Async self-invocation from handle_run_task_request (not logged: contains a bearer token)
    if 'run_task_callback' in event:
        process_run_task(event['run_task_callback'])
        return {'status': 'ok'}

    # Extract payload and headers
    body = event.get('body', '')
    if event.get('isBase64Encoded'):
        import base64
        body = base64.b64decode(body).decode('utf-8')
    
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}

    if 'x-tfc-task-signature' in headers:
        print("Received TFC run task request")
        return handle_run_task_request(body, headers['x-tfc-task-signature'], context)

    print(f"Received event: {json.dumps(event)}")
    
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

            # Covers the (signed) verification request sent when the notification is enabled
            if not event_type.startswith('run:'):
                print(f"Ignoring TFC notification trigger {event_type}")
                continue
            
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
