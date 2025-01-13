import boto3
import json
import base64
import urllib.parse
import random
from io import BytesIO
from prompt_generator import generate_enhanced_prompt
import os

def get_random_camera_movement():
    """
    Randomly select a camera movement from the predefined list
    
    Returns:
        str: A randomly selected camera movement description
    """
    CAMERA_MOVEMENTS = [
        "a shot taken from a drone or aircraft (FPV: first person view)",
        "camera moves in a circular path around a centrol point or an object",
        "camera rotates in the clockwise direction",
        "camera rotates in the counterclockwise direction",
        "moving the camera forward",
        "moving the camera backward",
        "camera sweeps to the left from a fixed position",
        "camera sweeps to the right from a fixed position",
        "fast pan shot",
        "moving camera down",
        "moving camera up",
        "camera does not move. Note that object or subject in the video can still move",
        "camera sweeps down from a fixed position",
        "camera sweeps up from a fixed position",
        "fast tilt shot",
        "moving camera towards left",
        "moving camera towards right",
        "focal length of a camera lens is adjusted to give the illusion of moving closer to the subject",
        "focal length of a camera lens is adjusted to give the illusion of moving further away from the subject",
        "fast zoom in or zoom out",
        "Use dolly and zoom at the same time to keep object size the same with dolly out + zoom in",
        "Use dolly and zoom at the same time to keep object size the same with dolly in + zoom out",
        "follows the subject at a constant distance"
    ]
    return random.choice(CAMERA_MOVEMENTS)

def update_item_with_nova_arn(table_name, taskid, sceneid, nova_arn):
    """
    Update DynamoDB item with nova-reel invocation ARN
    
    Args:
        table_name (str): The name of the DynamoDB table
        taskid (str): The taskId of the item
        sceneid (str): The sceneId of the item
        nova_arn (str): The nova-reel invocation ARN
    """
    try:
        # Initialize DynamoDB with region
        dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table(table_name)
        
        response = table.update_item(
            Key={
                'taskid': taskid,
                'sceneid': sceneid
            },
            UpdateExpression='SET #nova_arn = :nova_arn',
            ExpressionAttributeNames={
                '#nova_arn': 'nova-arn'
            },
            ExpressionAttributeValues={
                ':nova_arn': nova_arn
            }
        )
        print(f"Updated item with nova-arn: {nova_arn}")
        
    except Exception as e:
        print(f"Error updating DynamoDB item: {str(e)}")

def get_image_from_s3(image_uri):
    """
    Download image from S3 using the image-uri and convert to base64
    
    Args:
        image_uri (str): S3 URI of the image (s3://bucket/key)
        
    Returns:
        str: Base64 encoded image data
    """
    try:
        s3 = boto3.client('s3')
        
        # Parse the S3 URI
        parsed_uri = urllib.parse.urlparse(image_uri)
        bucket = parsed_uri.netloc
        key = parsed_uri.path.lstrip('/')
        
        # Download the image from S3
        response = s3.get_object(Bucket=bucket, Key=key)
        image_data = response['Body'].read()
        
        # Convert to base64
        base64_image = base64.b64encode(image_data).decode('utf-8')
        return base64_image
        
    except Exception as e:
        print(f"Error downloading image from S3: {str(e)}")
        return None

def lambda_handler(event, context):
    # Handle API Gateway request
    if 'body' in event:
        try:
            body = json.loads(event['body'])
            task_id = body.get('taskId')
            scene_id = body.get('sceneId')
        except (json.JSONDecodeError, AttributeError):
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid request body'})
            }
    else:
        task_id = event.get('taskId')
        scene_id = None
    
    if not task_id:
        return {
            'error': 'taskId is required'
        }
        
    # Initialize DynamoDB with region
    dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    table_name = os.environ['DYNAMODB_TABLE']
    table = dynamodb.Table(table_name)
    
    try:
        # If sceneId is provided, process only that specific scene
        if scene_id:
            response = table.get_item(
                Key={
                    'taskid': task_id,
                    'sceneid': scene_id
                }
            )
            item = response.get('Item')
            if not item:
                return {
                    'error': f'No item found for taskId: {task_id} and sceneId: {scene_id}'
                }
            
            try:
                generate_video_for_item(item, table_name)
                return {
                        'taskId': task_id,
                        'sceneId': scene_id,
                        'status': 'Processing'
                }
            except Exception as e:
                print(f"Failed to process item {scene_id}: {str(e)}")
                return {
                        'error': str(e),
                        'taskId': task_id,
                        'sceneId': scene_id
                }
        
        # If no sceneId provided, process all scenes (original behavior)
        response = table.query(
            KeyConditionExpression='taskid = :tid',
            ExpressionAttributeValues={
                ':tid': task_id
            }
        )
        items = response.get('Items', [])
        
        if not items:
            return {
                'error': f'No items found for taskId: {task_id}'
            }
            
        for item in items:
            try:
                generate_video_for_item(item, table_name)
            except Exception as e:
                print(f"Failed to process item {item.get('sceneid')}: {str(e)}")
                continue
            
        return {
                'taskId': task_id,
                'itemCount': len(items),
                'status': 'Processing'
        }
        
    except Exception as e:
        print(f"Error processing task: {str(e)}")
        return {
                'error': str(e),
                'taskId': task_id
        }

def generate_video_for_item(item, table_name):
    """
    Generate a video using nova-reel based on the Description and image from DDB item
    
    Args:
        item (dict): DynamoDB item containing Description and image-uri fields
    """
    try:
        # Create the Bedrock Runtime client
        bedrock_runtime = boto3.client("bedrock-runtime")
        text = item.get("text", "")
        taskid = item.get("taskid", "")
        sceneid = item.get('sceneid', '')
        description = item.get('Description', '')
        image_uri = item.get('image-uri', '')
        
        if not description:
            print("Warning: No Description found in item")
            return
            
        task = 'image-to-video'
        if sceneid =='0':
            prompt, _ = generate_enhanced_prompt(task,f"a picture for {text} by author {description}")
        else:
            prompt, _ = generate_enhanced_prompt(task,description)
        print("generate_video_for_item_from_image:",prompt)
        if not image_uri:
            print("Warning: No image-uri found in item")
            return
            
        # Get the image from S3 and convert to base64
        base64_image = get_image_from_s3(image_uri)
        if not base64_image:
            print("Error: Failed to get image from S3")
            return
            
        model_input = {
            "taskType": "TEXT_VIDEO",
            "textToVideoParams": {
                "text": prompt,
                "images": [
                    {
                        "format": "png",  # Assuming PNG format, adjust if needed
                        "source": {
                            "bytes": base64_image
                        }
                    }
                ]
            },
            "videoGenerationConfig": {
                "durationSeconds": 6,
                "fps": 24,
                "dimension": "1280x720",
                "seed": 0,
            },
        }
        
        # Start the asynchronous video generation job
        invocation = bedrock_runtime.start_async_invoke(
            modelId="amazon.nova-reel-v1:0",
            modelInput=model_input,
            outputDataConfig={
                "s3OutputDataConfig": {
                    "s3Uri": f"s3://bedrock.lijinhong.cn/nova-videos/{taskid}/"
                }
            }
        )
        
        # Get the invocation ARN from the response
        invocation_arn = invocation.get('invocationArn')
        
        print(f"Started video generation for scene: {item.get('sceneid', 'unknown')}")
        print(f"Job details: {json.dumps(invocation, indent=2, default=str)}")
        
        # Update DDB item with nova-arn
        if invocation_arn:
            update_item_with_nova_arn(
                table_name,
                item.get('taskid'),
                item.get('sceneid'),
                invocation_arn
            )
        
    except Exception as e:
        if hasattr(e, 'response'):
            message = e.response.get("Error", {}).get("Message", str(e))
            print(f"Error generating video: {message}")
        else:
            print(f"Error generating video: {str(e)}")
