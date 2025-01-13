import boto3
import json

def check_dynamodb_items(taskid):
    """Check items in DynamoDB for the given taskId"""
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('GenAIBuilderTable')
    
    try:
        response = table.query(
            KeyConditionExpression='taskid = :tid',
            ExpressionAttributeValues={':tid': taskid}
        )
        print("\nDynamoDB Items:")
        for item in response.get('Items', []):
            print(f"Scene {item.get('sceneid')}:")
            print(f"  Video URI: {item.get('video_uri')}")
            print(f"  Audio URI: {item.get('polly-uri')}")
            print(f"  Text: {item.get('text')}")
    except Exception as e:
        print(f"Error querying DynamoDB: {str(e)}")

def invoke_lambda():
    # Initialize AWS Lambda client
    lambda_client = boto3.client('lambda', region_name='us-east-1')

    # Extract taskId from the ARN
    task_id = ''
    function_name = ''

    # First, check DynamoDB items
    print(f"\nChecking DynamoDB items for taskId: {task_id}")
    check_dynamodb_items(task_id)

    # Test event with the specified taskId
    event = {
        'taskId': task_id,
        'output': 'output_combined.mp4'
    }

    try:
        print("\nInvoking Lambda function...")
        # Invoke the Lambda function
        response = lambda_client.invoke(
            FunctionName=function_name,  # Replace XXXXXXXX with the actual function suffix
            InvocationType='RequestResponse',
            LogType='Tail',  # Include the execution log in the response
            Payload=json.dumps(event)
        )
        
        # Get the log output
        log_result = response.get('LogResult')
        if log_result:
            import base64
            print("\nFunction Logs:")
            print(base64.b64decode(log_result).decode('utf-8'))
        
        # Read and parse the response
        response_payload = json.loads(response['Payload'].read().decode('utf-8'))
        print("\nLambda function response:", json.dumps(response_payload, indent=2))

    except Exception as e:
        print(f"\nError invoking Lambda function: {str(e)}")

if __name__ == '__main__':
    invoke_lambda()
