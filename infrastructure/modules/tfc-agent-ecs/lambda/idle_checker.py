"""
TFC Agent Idle Checker

Runs on a schedule to stop agents that have been idle too long.
Agents that TFC reports as busy are kept alive regardless of webhook activity.
"""

import json
import os
import urllib.parse
import urllib.request
import boto3
from datetime import datetime, timezone, timedelta

# Environment variables
CLUSTER_ARN = os.environ['CLUSTER_ARN']
TABLE_NAME = os.environ['TABLE_NAME']
IDLE_TIMEOUT_MINUTES = int(os.environ.get('IDLE_TIMEOUT_MINUTES', '15'))
TFC_ADDRESS = os.environ.get('TFC_ADDRESS', 'app.terraform.io')
TFC_AGENT_POOL_ID = os.environ.get('TFC_AGENT_POOL_ID', '')
TFC_API_TOKEN_SECRET_ARN = os.environ.get('TFC_API_TOKEN_SECRET_ARN', '')

# AWS clients
ecs = boto3.client('ecs')
secretsmanager = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)


def get_running_agents() -> list:
    """Get list of currently running agent records from DynamoDB."""
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


def stop_agent(task_arn: str, reason: str):
    """Stop an ECS task."""
    try:
        ecs.stop_task(
            cluster=CLUSTER_ARN,
            task=task_arn,
            reason=reason
        )
        print(f"Stopped agent {task_arn}: {reason}")
        return True
    except Exception as e:
        print(f"Error stopping task {task_arn}: {e}")
        return False


def mark_agent_stopped(pk: str, sk: str):
    """Update DynamoDB record to mark agent as stopped."""
    try:
        table.update_item(
            Key={'pk': pk, 'sk': sk},
            UpdateExpression='SET #s = :status, stopped_at = :now',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':status': 'stopped',
                ':now': datetime.now(timezone.utc).isoformat()
            }
        )
    except Exception as e:
        print(f"Error updating agent record: {e}")


def check_task_status(task_arn: str) -> str:
    """Get the current status of an ECS task."""
    try:
        response = ecs.describe_tasks(
            cluster=CLUSTER_ARN,
            tasks=[task_arn]
        )
        if response['tasks']:
            return response['tasks'][0]['lastStatus']
        return 'NOT_FOUND'
    except Exception as e:
        print(f"Error checking task {task_arn}: {e}")
        return 'ERROR'


def get_busy_agent_names(now: datetime):
    """Return names of agents TFC reports as busy, or None if status is unavailable."""
    if not TFC_AGENT_POOL_ID or not TFC_API_TOKEN_SECRET_ARN:
        return None
    try:
        token = secretsmanager.get_secret_value(SecretId=TFC_API_TOKEN_SECRET_ARN)['SecretString']
        since = (now - timedelta(minutes=IDLE_TIMEOUT_MINUTES)).strftime('%Y-%m-%dT%H:%M:%SZ')
        query = urllib.parse.urlencode({'filter[last-ping-since]': since, 'page[size]': '100'})
        request = urllib.request.Request(
            f"https://{TFC_ADDRESS}/api/v2/agent-pools/{TFC_AGENT_POOL_ID}/agents?{query}",
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/vnd.api+json'
            }
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            agents = json.load(response).get('data', [])
        busy = {
            a['attributes'].get('name')
            for a in agents
            if a.get('attributes', {}).get('status') == 'busy'
        }
        print(f"TFC reports {len(busy)} busy agent(s): {sorted(n for n in busy if n)}")
        return busy
    except Exception as e:
        print(f"Could not read agent status from TFC, using idle timeout only: {e}")
        return None


def touch_agent(pk: str, sk: str, now: datetime):
    """Reset an agent's idle timer."""
    try:
        table.update_item(
            Key={'pk': pk, 'sk': sk},
            UpdateExpression='SET last_activity = :now',
            ExpressionAttributeValues={':now': now.isoformat()}
        )
    except Exception as e:
        print(f"Error updating agent activity: {e}")


def handler(event, context):
    """Lambda handler for scheduled idle check."""
    print(f"Running idle check with {IDLE_TIMEOUT_MINUTES} minute timeout")
    
    agents = get_running_agents()
    print(f"Found {len(agents)} agent records")
    
    now = datetime.now(timezone.utc)
    idle_threshold = now - timedelta(minutes=IDLE_TIMEOUT_MINUTES)
    
    stopped_count = 0
    cleaned_count = 0
    busy_count = 0
    busy_agents = None
    busy_agents_loaded = False
    
    for agent in agents:
        task_arn = agent['task_arn']
        pk = agent['pk']
        sk = agent['sk']
        
        # Check actual ECS task status
        status = check_task_status(task_arn)
        
        if status in ['STOPPED', 'NOT_FOUND', 'ERROR']:
            # Task already stopped - clean up record
            print(f"Agent {task_arn} already stopped (status: {status})")
            mark_agent_stopped(pk, sk)
            cleaned_count += 1
            continue
        
        # Check last activity time
        last_activity_str = agent.get('last_activity', agent.get('started_at'))
        try:
            last_activity = datetime.fromisoformat(last_activity_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            print(f"Invalid last_activity for {task_arn}, using now")
            last_activity = now
        
        if last_activity < idle_threshold:
            # Only call the TFC API when an agent is actually due to be stopped
            if not busy_agents_loaded:
                busy_agents = get_busy_agent_names(now)
                busy_agents_loaded = True

            agent_name = agent.get('agent_name')
            if busy_agents is not None and agent_name and agent_name in busy_agents:
                print(f"Agent {task_arn} ({agent_name}) is busy in TFC, keeping alive")
                touch_agent(pk, sk, now)
                busy_count += 1
                continue

            # Agent has been idle too long - stop it
            print(f"Agent {task_arn} idle since {last_activity}, stopping")
            if stop_agent(task_arn, f"Idle for more than {IDLE_TIMEOUT_MINUTES} minutes"):
                mark_agent_stopped(pk, sk)
                stopped_count += 1
        else:
            idle_minutes = (now - last_activity).total_seconds() / 60
            print(f"Agent {task_arn} active {idle_minutes:.1f} minutes ago, keeping alive")
    
    result = {
        'checked': len(agents),
        'stopped': stopped_count,
        'cleaned': cleaned_count,
        'busy': busy_count
    }
    print(f"Idle check complete: {result}")
    return result
