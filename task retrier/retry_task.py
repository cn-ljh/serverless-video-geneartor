import boto3
import json
import os

def lambda_handler(event, context):
    """
    Lambda handler for retrying tasks
    
    Expected event format from API Gateway proxy integration:
    {
        "body": {
            "taskId": "required-task-id",
            "sceneId": "required-scene-id",
            "audio": true/false (optional),
            "video": true/false (optional),
            "image": true/false (optional)
        }
    }
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
        
        # Validate required parameters
        task_id = body.get('taskId')
        scene_id = body.get('sceneId')
        
        if not task_id or not scene_id:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'error': 'taskId and sceneId are required in the request body'
                })
            }
        
        # Get optional parameters
        retry_audio = body.get('audio', False)
        retry_video = body.get('video', False)
        retry_image = body.get('image', False)
        
        # If image needs to be retried, video must also be retried
        # if retry_image:
        #     retry_video = True
        
        lambda_client = boto3.client('lambda')
        retried_functions = []
        
        # If image retry is requested, invoke image generator first
        if retry_image:
            try:
                response = lambda_client.invoke(
                    FunctionName=os.environ['IMAGE_GENERATOR_FUNCTION'],
                    InvocationType='Event',  # Asynchronous invocation
                    Payload=json.dumps({
                        'body': json.dumps({
                            'taskId': task_id,
                            'sceneId': scene_id
                        })
                    })
                )
                retried_functions.append('image')
            except Exception as e:
                print(f"Error invoking image generator: {str(e)}")
                raise
        
        # Retry video generation if requested
        if retry_video:
            try:
                response = lambda_client.invoke(
                    FunctionName=os.environ['VIDEO_GENERATOR_FUNCTION'],
                    InvocationType='Event',  # Asynchronous invocation
                    Payload=json.dumps({
                        'body': json.dumps({
                            'taskId': task_id,
                            'sceneId': scene_id
                        })
                    })
                )
                retried_functions.append('video')
            except Exception as e:
                print(f"Error invoking video generator: {str(e)}")
                raise
        
        # Retry audio generation if requested
        if retry_audio:
            try:
                response = lambda_client.invoke(
                    FunctionName=os.environ['SPEECH_GENERATOR_FUNCTION'],
                    InvocationType='Event',  # Asynchronous invocation
                    Payload=json.dumps({
                        'body': json.dumps({
                            'taskId': task_id,
                            'sceneId': scene_id
                        })
                    })
                )
                retried_functions.append('audio')
            except Exception as e:
                print(f"Error invoking speech generator: {str(e)}")
                raise
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'taskId': task_id,
                'sceneId': scene_id,
                'status': 'RETRY_INITIATED',
                'retried_functions': retried_functions
            })
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
