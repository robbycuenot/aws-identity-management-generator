"""
TFC Agent Idle Checker

Runs on a schedule to stop agents that have been idle too long.
"""

import os
import boto3
from datetime import datetime, timezone, timedelta

# Environment variables
CLUSTER_ARN = os.environ['CLUSTER_ARN']
TABLE_NAME = os.environ['TABLE_NAME']
IDLE_TIMEOUT_MINUTES = int(os.environ.get('IDLE_TIMEOUT_MINUTES', '15'))

# AWS clients
ecs = boto3.client('ecs')
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


def handler(event, context):
    """Lambda handler for scheduled idle check."""
    print(f"Running idle check with {IDLE_TIMEOUT_MINUTES} minute timeout")
    
    agents = get_running_agents()
    print(f"Found {len(agents)} agent records")
    
    now = datetime.now(timezone.utc)
    idle_threshold = now - timedelta(minutes=IDLE_TIMEOUT_MINUTES)
    
    stopped_count = 0
    cleaned_count = 0
    
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
        'cleaned': cleaned_count
    }
    print(f"Idle check complete: {result}")
    return result
