import base64
import io
import json
import logging
import boto3
import os
from PIL import Image
from botocore.config import Config
from botocore.exceptions import ClientError
from prompt_generator import generate_enhanced_prompt

class ImageError(Exception):
    "Custom exception for errors returned by Amazon Nova Canvas"
    def __init__(self, message):
        self.message = message

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def upload_to_s3(image_bytes, taskid, sceneid):
    """
    Upload image to S3
    
    Args:
        image_bytes (bytes): The image data to upload
        taskid (str): The task ID
        sceneid (str): The scene ID
    
    Returns:
        str: The S3 URI where the image was uploaded
    """
    try:
        # Create S3 client
        s3 = boto3.client('s3')
        bucket = 'bedrock.lijinhong.cn'
        key = f"nova-image/{taskid}/{sceneid}.png"
        
        # Upload the image
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=image_bytes,
            ContentType='image/png'
        )
        
        s3_uri = f"s3://{bucket}/{key}"
        logger.info(f"Uploaded image to {s3_uri}")
        return s3_uri
        
    except Exception as e:
        logger.error(f"Error uploading to S3: {str(e)}")
        raise

def update_item_with_image_info(table_name, taskid, sceneid, s3_uri, prompt, negative_prompt, status="SUCCESS"):
    """
    Update DynamoDB item with image S3 URI and status
    
    Args:
        table_name (str): The name of the DynamoDB table
        taskid (str): The taskId of the item
        sceneid (str): The sceneId of the item
        s3_uri (str): The S3 URI where the image is stored or error message if failed
        status (str): Status of the image generation (SUCCESS or FAILED)
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
            UpdateExpression='SET #image_uri = :image_uri, #prompt = :prompt, #negative_prompt = :negative_prompt, #image_status = :image_status',
            ExpressionAttributeNames={
                '#image_uri': 'image-uri',
                '#prompt':'prompt',
                '#negative_prompt':'negative_prompt',
                '#image_status': 'image_status'
            },
            ExpressionAttributeValues={
                ':image_uri': s3_uri,
                ':prompt': prompt,
                ':negative_prompt': negative_prompt,
                ':image_status': status
            }
        )
        logger.info(f"Updated item with image URI: {s3_uri}")
        
    except Exception as e:
        logger.error(f"Error updating DynamoDB item: {str(e)}")

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
            'statusCode': 400,
            'body': json.dumps({'error': 'taskId is required'})
        }
        
    # Initialize DynamoDB with region
    dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    table_name = os.environ['DYNAMODB_TABLE']
    table = dynamodb.Table(table_name)
    
    try:
        # If sceneId is provided, query only that specific scene
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
                    'statusCode': 404,
                    'body': json.dumps({'error': f'No item found for taskId: {task_id} and sceneId: {scene_id}'})
                }
            
            try:
                generate_image_for_item(item, table_name)
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'taskId': task_id,
                        'sceneId': scene_id,
                        'status': 'Processing'
                    })
                }
            except Exception as e:
                logger.error(f"Failed to process item {scene_id}: {str(e)}")
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': str(e),
                        'taskId': task_id,
                        'sceneId': scene_id
                    })
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
            
        failed_items = 0
        for item in items:
            try:
                generate_image_for_item(item, table_name)
            except Exception as e:
                logger.error(f"Failed to process item {item.get('sceneid')}: {str(e)}")
                failed_items += 1
                continue
            
        return {
                'taskId': task_id,
                'itemCount': len(items),
                'failedItems': failed_items,
                'status': 'Processing'
        }
        
    except Exception as e:
        logger.error(f"Error processing task: {str(e)}")
        return {
                'error': str(e),
                'taskId': task_id
        }

def generate_image_for_item(item, table_name):
    """
    Generate an image using nova-canvas based on the Description from DDB item
    
    Args:
        item (dict): DynamoDB item containing Description field
        table_name (str): The name of the DynamoDB table
    """
    prompt = ""
    negative_prompt = ""
    try:
        taskid=item.get('taskid')
        sceneid=item.get('sceneid')
        text=item.get('text')
        description = item.get('Description', '')
        if not description:
            error_msg = "No Description found in item"
            logger.warning(error_msg)
            update_item_with_image_info(
                table_name,
                taskid,
                sceneid,
                f"Failed: {error_msg}",
                prompt,
                negative_prompt,
                "FAILED"
            )
            return
            
        # Create the Bedrock Runtime client with extended timeout
        bedrock = boto3.client(
            service_name='bedrock-runtime',
            config=Config(read_timeout=300)
        )
        
        # Get enhanced prompt from Nova
        task = 'text-to-image'
        if sceneid =='0':
            prompt,negative_prompt = generate_enhanced_prompt(task,f"a picture for {text} by author {description}")
        else:
            prompt,negative_prompt = generate_enhanced_prompt(task,description)
        print("negative_prompt in image_generator:", negative_prompt)
        
        # Prepare the request body
        body = json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt,
                "negativeText":negative_prompt
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 720,
                "width": 1280,
                "cfgScale": 8.0,
                "seed": 0
            }
        })
        
        # Call the model
        logger.info(f"Generating image for scene: {item.get('sceneid', 'unknown')}")
        response = bedrock.invoke_model(
            body=body,
            modelId="amazon.nova-canvas-v1:0",
            accept="application/json",
            contentType="application/json"
        )
    
        # Process the response
        response_body = json.loads(response.get("body").read())
        
        # Check for errors
        if response_body.get("error") is not None:
            raise ImageError(f"Image generation error: {response_body.get('error')}")
        
        # Get the base64 image and decode it
        base64_image = response_body.get("images")[0]
        base64_bytes = base64_image.encode('ascii')
        image_bytes = base64.b64decode(base64_bytes)
        
        # Upload to S3 and update DynamoDB
        s3_uri = upload_to_s3(
            image_bytes,
            taskid,
            sceneid
        )
        
        update_item_with_image_info(
            table_name,
            taskid,
            sceneid,
            s3_uri,
            prompt,
            negative_prompt
        )
    
        logger.info(f"Successfully generated and saved image for scene: {item.get('sceneid', 'unknown')}")
    
    except ClientError as err:
        message = err.response["Error"]["Message"]
        logger.error(f"A client error occurred: {message}")
        update_item_with_image_info(
            table_name,
            item.get('taskid'),
            item.get('sceneid'),
            f"Failed: {message}",
            prompt,
            negative_prompt,
            "FAILED"
        )
        raise
    except ImageError as err:
        logger.error(err.message)
        update_item_with_image_info(
            table_name,
            item.get('taskid'),
            item.get('sceneid'),
            f"Failed: {err.message}",
            prompt,
            negative_prompt,
            "FAILED"
        )
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error generating image: {error_msg}")
        update_item_with_image_info(
            table_name,
            item.get('taskid'),
            item.get('sceneid'),
            f"Failed: {error_msg}",
            prompt,
            negative_prompt,
            "FAILED"
        )
        raise
