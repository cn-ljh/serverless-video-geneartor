import boto3
import json
import os

def update_item_with_polly_info(table_name, taskid, sceneid, task_id, output_uri):
    """
    Update DynamoDB item with Polly task information
    
    Args:
        table_name (str): The name of the DynamoDB table
        taskid (str): The taskId of the item
        sceneid (str): The sceneId of the item
        task_id (str): The Polly synthesis task ID
        output_uri (str): The S3 URI of the generated audio file
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
            UpdateExpression='SET #polly_task = :task_id, #polly_uri = :output_uri',
            ExpressionAttributeNames={
                '#polly_task': 'polly-task',
                '#polly_uri': 'polly-uri'
            },
            ExpressionAttributeValues={
                ':task_id': task_id,
                ':output_uri': output_uri
            }
        )
        print(f"Updated item with Polly task ID: {task_id}")
        print(f"Updated item with Polly output URI: {output_uri}")
        
    except Exception as e:
        print(f"Error updating DynamoDB item with Polly info: {str(e)}")

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
                generate_speech_for_item(item, table_name)
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

        # If no sceneId provided, process all scenes
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
                generate_speech_for_item(item, table_name)
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

def generate_speech_for_item(item, table_name):
    """
    Generate speech from text using Amazon Polly
    
    Args:
        item (dict): DynamoDB item containing original text and other fields
        table_name (str): The name of the DynamoDB table
    """
    try:
        # Extract required fields
        original_text = item.get('text', '')
        taskid = item.get('taskid')
        sceneid = item.get('sceneid')
        language = item.get('language')
        
        if not original_text:
            print("Warning: No text found in item")
            return
            
        # Create an Amazon Polly client
        polly_client = boto3.client('polly')
        ssml_text = f"""<speak>
            <break time="1000ms"/>
            <prosody rate="slow" volume="loud">
                {original_text}
            </prosody>
            <break time="500ms"/>
        </speak>"""
        # Get SSML and language settings
        if language == "Chinese":
            voice_id = "Zhiyu"
            language_code = "cmn-CN"
            
            response = polly_client.start_speech_synthesis_task(
                TextType='ssml',
                Text=ssml_text,
                OutputFormat='mp3',
                OutputS3BucketName='bedrock.lijinhong.cn',
                OutputS3KeyPrefix=f"polly-audio/{taskid}/",
                VoiceId=voice_id,
                LanguageCode=language_code,
                Engine='standard'
            )
        elif language == "English":
            voice_id = "Joanna"
            language_code = "en-US"
            try:
                response = polly_client.start_speech_synthesis_task(
                    TextType='ssml',
                    Text=ssml_text,
                    OutputFormat='mp3',
                    OutputS3BucketName='bedrock.lijinhong.cn',
                    OutputS3KeyPrefix=f"polly-audio/{taskid}/",
                    VoiceId=voice_id,
                    LanguageCode=language_code,
                    Engine='neural'
                )
            except polly_client.exceptions.EngineNotSupportedException as e:
                print(f"Neural engine not supported for {voice_id}, falling back to standard engine")
                response = polly_client.start_speech_synthesis_task(
                    TextType='ssml',
                    Text=ssml_text,
                    OutputFormat='mp3',
                    OutputS3BucketName='bedrock.lijinhong.cn',
                    OutputS3KeyPrefix=f"polly-audio/{taskid}/",
                    VoiceId=voice_id,
                    LanguageCode=language_code,
                    Engine='standard'
                )
        else:
            print("unsupported language")
            return
            
        # Get the task ID and output URI
        task_id = response['SynthesisTask']['TaskId']
        output_uri = response['SynthesisTask']['OutputUri']
        
        print(f"Started speech synthesis task: {task_id}")
        print(f"Output will be available at: {output_uri}")
        
        # Update DDB with Polly information
        update_item_with_polly_info(table_name, taskid, sceneid, task_id, output_uri)
            
    except polly_client.exceptions.ServiceFailureException as e:
        print(f"Polly service failure: {str(e)}")
        raise
    except polly_client.exceptions.LexiconNotFoundException as e:
        print(f"Lexicon not found: {str(e)}")
        raise
    except polly_client.exceptions.MaxLexemeLengthExceededException as e:
        print(f"Max lexeme length exceeded: {str(e)}")
        raise
    except polly_client.exceptions.MaxLexiconsNumberExceededException as e:
        print(f"Max lexicons number exceeded: {str(e)}")
        raise
    except polly_client.exceptions.TextLengthExceededException as e:
        print(f"Text length exceeded: {str(e)}")
        raise
    except polly_client.exceptions.InvalidSsmlException as e:
        print(f"Invalid SSML: {str(e)}")
        raise
    except Exception as e:
        print(f"Error starting speech synthesis task: {str(e)}")
        raise
