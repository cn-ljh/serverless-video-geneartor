import boto3
import os
from boto3.dynamodb.conditions import Key

def scan_task_items(task_id, table_name):
    """
    Scan DynamoDB table for all items with a specific taskId
    
    Args:
        task_id (str): The taskId to query for
        table_name (str): The name of the DynamoDB table
        
    Returns:
        list: List of items matching the taskId
    """
    # Initialize DynamoDB resource with region
    dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    table = dynamodb.Table(table_name)
    
    try:
        # Query the table using the partition key (taskid)
        response = table.query(
            KeyConditionExpression=Key('taskid').eq(task_id),
            ConsistentRead=True
        )
        
        items = response['Items']
        
        # Handle pagination if there are more items
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('taskid').eq(task_id),
                ExclusiveStartKey=response['LastEvaluatedKey'],
                ConsistentRead=True
            )
            items.extend(response['Items'])
            
        return items
        
    except Exception as e:
        print(f"Error querying DynamoDB: {str(e)}")
        return []

def lambda_handler(event, context):
    """
    Lambda handler for task initialization. This function validates that the task exists
    and its data is ready for processing by subsequent Lambda functions.
    """
    task_id = event.get('taskId')
    
    if not task_id:
        raise ValueError("taskId is required in the event input")
    
    # Get table name from environment variable
    table_name = os.environ['DYNAMODB_TABLE']
    results = scan_task_items(task_id, table_name)
    
    if not results:
        raise ValueError(f"No items found for taskId: {task_id}")
        
    print(f"Found {len(results)} items for taskId: {task_id}")
    
    # Return task info for parallel processing
    return {
        'taskId': task_id,
        'itemCount': len(results)
    }
