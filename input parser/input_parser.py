import json
import boto3
import os
import uuid
from datetime import datetime

class InputParserError(Exception):
    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.status_code = status_code

def lambda_handler(event, context):
    try:
        # The event is already the body due to InputPath: "$.body" in the state machine
        if isinstance(event, str):
            body = json.loads(event)
        else:
            body = event
        prompt = body.get('prompt')
        
        if not prompt:
            raise InputParserError('Prompt is required in the request body', 400)
        # Split prompt into lines and remove empty lines
        prompt_lines = [line.strip() for line in prompt.split('\n') if line.strip()]        
        print(prompt_lines)
        
        messages = []
        model_id = "amazon.nova-lite-v1:0"

        # Initialize Bedrock client
        bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=os.environ.get('AWS_REGION', 'us-east-1')
        )

        # Combine system instructions with user prompt
        system_instructions = [
            {
                "text":"""
You are abilingual literary scholar who is proficient in both Chinese and English. 
##You excel in the following areas:##
You are good at understanding Chinese Classical Poetry.
You are good at split the poem into different scenes based on its content.
You are good at provide a concise English description for each scene that maintains the original poetic atmosphere. 
These scenes and descriptions will be used for subsequent video content creation.

####Your prompt rewriting should follow these guidelines:##
The English description should maintain the original text atmosphere and be concise and clear.
Ensure that each scene is independent yet cohesive overall, fully expressing the content of the poem.
No Chinese character should be contained in the english description.
Don't contain any Amazon Bedrock filter words. 
The language choise in output can only be Chinese or English. If other language detected, you should output error message.

##Input Format:##
[Title-Author]
[Content]

##Output Format:##
{
  "Scene 0": {
    "text": "title - author",
    "Description": "title's descrition with author info",
    "language": "Chinese/English"
  },
  "Scene 1": {
    "text": "Scene's origin text",
    "Description": "Scene's English Description",
    "language": "Chinese/English"
  },
  "Scene 2": {
    "text": "cene's origin text",
    "Description": "Scene's English Description",
    "language": "Chinese/English"
  }
}

##Example:##
###Example 1:###
####user input:####
《静夜思》- 李白
床前明月光，疑是地上霜。
举头望明月，低头思故乡。
####model output:####
{
  "Scene 0": {
    "text": "《静夜思》- 李白",
    "Description": "Under the moonlit night, Li Bai gazing at the moon and thinking of home.",
    "language": "Chinese"
  },
  "Scene 1": {
    "text": "床前明月光",
    "Description": "At night, lying in bed, the moonlight spills onto the floor.",
    "language": "Chinese"
  },
  "Scene 2": {
    "text": "疑是地上霜",
    "Description": "Mistakenly thinking there is a layer of frost on the ground.",
    "language": "Chinese"
  },
  "Scene 3": {
    "text": "举头望明月",
    "Description": "Looking up at the bright moon outside the window.",
    "language": "Chinese"
  },
  "Scene 4": {
    "text": "低头思故乡",
    "Description": "Lowering head, immersed in homesickness.",
    "language": "Chinese"
  }
}
###Example 2:###
####user input:####
Quiet Night Thoughts - Bai Li
Bright moonlight before my bed,
I suspect it is frost on the ground.
I raise my head to view the bright moon,
And lower it, thinking of my hometown.
####model output:####
{
  "Scene 0": {
    "text": "Quiet Night Thoughts - Bai Li",
    "Description": "Under the moonlit night, Li Bai gazing at the moon and thinking of home.",
    "language": "English"
  },
  "Scene 1": {
    "text": "Bright moonlight before my bed",
    "Description": "At night, lying in bed, the moonlight spills onto the floor.",
    "language": "English"
  },
  "Scene 2": {
    "text": "I suspect it is frost on the ground",
    "Description": "Mistakenly thinking there is a layer of frost on the ground.",
    "language": "English"
  },
  "Scene 3": {
    "text": "I raise my head to view the bright moon",
    "Description": "Looking up at the bright moon outside the window.",
    "language": "English"
  },
  "Scene 4": {
    "text": "And lower it, thinking of my hometown",
    "Description": "Lowering head, immersed in homesickness.",
    "language": "English"
  }
}
##Ouput instruction##

Users may input prompts in Chinese or English. You should output the content exactly match the output format. Make sure the text and the language are matched.
"""}]

        # Add combined prompt
        messages.append({
            "role": "user",
            "content": [{
                "text": f"Please analyze:\n{prompt}"
            }]
        })
        print("message:", messages)
        response = bedrock_client.converse(
            modelId=model_id,
            messages=messages,
            system=system_instructions,
            inferenceConfig={
                "temperature": 0.7,
                "topP": 0.9,
                "maxTokens": 1500
            }
        )

        # Extract the response
        output_message = response['output']['message']
        return_messages = []
        for content in output_message['content']:
            if 'text' in content:
                return_messages.append(content['text'])
        
        # Get Step Functions execution ID
        task_id = body.get('executionId', str(uuid.uuid4()))
        #the task_id is too long, arn:aws:states:us-east-1:778346837945:execution:StepFunctionsStateMachine-wag32K5iW6Lr:96878e6d-015c-4572-9d24-920550e9ae09, I just need the last part
        task_id = task_id.split(':')[-1]

        # Initialize DynamoDB with region
        dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        table_name = os.environ['DYNAMODB_TABLE']
        table = dynamodb.Table(table_name)
        
        # Process and store scenes in DynamoDB
        for message in return_messages:
            try:
                # Parse the JSON response
                scenes_data = json.loads(message)
                
                # Store each scene in DynamoDB
                for scene_num, scene_content in scenes_data.items():
                    scene_id = scene_num.split()[-1]  # Extract number from "Scene X"
                    table.put_item(
                        Item={
                            'taskid': task_id,
                            'sceneid': scene_id,
                            'text': scene_content['text'],
                            'Description': scene_content['Description'],
                            'language': scene_content['language'],
                            'create_time': datetime.utcnow().isoformat()
                        }
                    )
                    
            except Exception as e:
                print(f"Error processing scenes: {e}")
                # Store error information in DynamoDB for debugging
                table.put_item(
                    Item={
                        'taskid': task_id,
                        'sceneid': '-1',
                        'text': message,
                        'Description': 'Error parsing scene data',
                        'language': scene_content['language'],
                        'create_time': datetime.utcnow().isoformat()
                    }
                )
                # Raise error to stop state machine with task_id
                raise InputParserError(f"Failed to process scene data for task {task_id}: {str(e)}", 500)

        # Return the task ID for Step Functions
        return {
            'taskId': task_id
        }

    except Exception as e:
        # Get task_id if available
        task_id = None
        try:
            if isinstance(event, dict):
                task_id = event.get('executionId')
            elif isinstance(event, str):
                task_id = json.loads(event).get('executionId')
        except:
            task_id = str(uuid.uuid4())  # Generate new task_id if not available
            
        if isinstance(e, InputParserError):
            error_msg = str(e)
            status_code = e.status_code
        else:
            error_msg = f"Internal server error: {str(e)}"
            status_code = 500
            
        error = {
            'error': error_msg,
            'type': type(e).__name__,
            'statusCode': status_code,
            'taskId': task_id
        }
        # Raise error to be caught by state machine
        raise Exception(json.dumps(error))
