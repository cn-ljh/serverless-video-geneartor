import os
import json
import boto3
from typing import Dict, Optional

def check_completed_status(items: list) -> bool:
    """
    Check if all tasks have completed status.
    
    Args:
        items: List of task items from DynamoDB
    
    Returns:
        bool: True if all tasks are completed, False otherwise
    """
    for item in items:
        audio_status = item.get('audio_status', '').lower()
        video_status = item.get('video_status', '').lower()
        image_status = item.get('image_status', '').lower()
        
        if not (audio_status == 'completed' and 
                video_status == 'Completed' and 
                image_status == 'success'):
            return False
    return True

def query_tasks(task_id: str) -> list:
    """
    Query tasks from DynamoDB for a given task ID.
    
    Args:
        task_id: The task ID to query for
    
    Returns:
        list: List of task information matching the task_id
    """
    # Initialize DynamoDB client
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ['TASKS_TABLE'])
    
    # Query the table for items with matching task_id (partition key)
    ddb_response = table.query(
        KeyConditionExpression='taskid = :tid',
        ExpressionAttributeValues={
            ':tid': task_id
        },
        ScanIndexForward=False  # Get latest items first
    )
    
    return ddb_response['Items']

def update_and_query_task_status(task_id: str) -> list:
    """
    Update task status via task_status_checker lambda and then query tasks from DynamoDB.
    
    Args:
        task_id: The task ID to query for
    
    Returns:
        list: List of task information matching the task_id
        
    Raises:
        Exception: If there's an error accessing DynamoDB or invoking Lambda
    """
    try:
        # Initialize Lambda client
        lambda_client = boto3.client('lambda')
        
        # Call task_status_checker lambda
        lambda_response = lambda_client.invoke(
            FunctionName=os.environ['TASK_STATUS_CHECKER_FUNCTION'],
            InvocationType='RequestResponse',
            Payload=json.dumps({'taskId': task_id})
        )
        
        # Parse lambda response
        status_response = json.loads(lambda_response['Payload'].read())
        if 'errorMessage' in status_response:
            raise Exception(f"Task status checker error: {status_response['errorMessage']}")
            
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(os.environ['TASKS_TABLE'])
        
        # Query the table for items with matching task_id (partition key)
        ddb_response = table.query(
            KeyConditionExpression='taskid = :tid',
            ExpressionAttributeValues={
                ':tid': task_id
            },
            ScanIndexForward=False  # Get latest items first
        )
        
        return ddb_response['Items']
            
    except Exception as e:
        print(f"Error in task status update and query: {str(e)}")
        print(f"Task ID: {task_id}")
        raise Exception(f"Operation failed: {str(e)}")

def lambda_handler(event, context):
    """
    Lambda handler to query task status by task ID.
    
    Expected event format from API Gateway proxy integration:
    {
        "body": "{"taskId": "string"}"
    }
    
    Returns:
        dict: API Gateway proxy response with list of tasks matching the task ID
    """
    # CORS headers for API Gateway response
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
    }
    
    try:
        # Parse the request body
        if not event.get('body'):
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'Request body is required'
                })
            }
            
        body = json.loads(event['body'])
        
        # Extract task ID from body
        if 'taskId' not in body:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'taskId is required in request body'
                })
            }
        
        task_id = body['taskId']
        
        # First query DynamoDB directly
        tasks = query_tasks(task_id)
        
        # Only update status if tasks are not all completed
        if not tasks or not check_completed_status(tasks):
            tasks = update_and_query_task_status(task_id)
            
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(tasks)
        }
        
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': headers,
            'body': json.dumps({
                'error': 'Invalid JSON in request body'
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'error': str(e)
            })
        }
