import boto3
import sys
from typing import Dict, Any
import os
import json

class TaskStatusChecker:
    def __init__(self):
        self.bedrock_runtime = boto3.client('bedrock-runtime')
        self.polly = boto3.client('polly')

    def get_tasks(self, task_id: str) -> list:
        """
        Query DynamoDB table for all scenes of a task
        """
        try:
            # Initialize DynamoDB with region
            dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
            table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
            
            response = table.query(
                KeyConditionExpression='taskid = :tid',
                ExpressionAttributeValues={
                    ':tid': task_id
                }
            )
            return response.get('Items', [])
        except Exception as e:
            print(f"Error querying DynamoDB: {str(e)}")
            return []

    def check_nova_status(self, job_arn: str) -> str:
        """
        Check the status of a Nova Reel job
        """
        try:
            response = self.bedrock_runtime.get_async_invoke(
                invocationArn=job_arn
            )
            status = response["status"]
            if (status == "Completed"):
                bucket_uri = response["outputDataConfig"]["s3OutputDataConfig"]["s3Uri"]
                video_uri = bucket_uri + "/output.mp4"
                print(f"Video is available at: {video_uri}")
                return status, video_uri

            elif (status == "InProgress"):
                start_time = response["submitTime"]
                print(f"Job {job_arn} is in progress. Started at: {start_time}")
                return status,'InProgress'
            elif (status == "Failed"):
                failure_message = response["failureMessage"]
                print(f"Job {job_arn} failed. Failure message: {failure_message}")
                return status,failure_message
        except Exception as e:
            print(f"Error checking Nova Reel status: {str(e)}")
            return 'ERROR'

    def check_polly_status(self, task_id: str) -> str:
        """
        Check the status of a Polly synthesis task
        """
        try:
            response = self.polly.get_speech_synthesis_task(TaskId=task_id)
            return response['SynthesisTask']['TaskStatus']
        except Exception as e:
            print(f"Error checking Polly status: {str(e)}")
            return 'ERROR'

    def update_task_status(self, task_id: str, scene_id: str, video_status: str,  video_uri: str, audio_status: str,):
        """
        Update the task status in DynamoDB
        """
        try:
            # Initialize DynamoDB with region
            dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
            table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
            
            table.update_item(
                Key={
                    'taskid': task_id,
                    'sceneid': scene_id
                },
                UpdateExpression='SET video_status = :vs, audio_status = :as, video_uri = :vu',
                ExpressionAttributeValues={
                    ':vs': video_status,
                    ':vu': video_uri,
                    ':as': audio_status
                }
            )
        except Exception as e:
            print(f"Error updating task status: {str(e)}")

    def process_task(self, task_id: str):
        """
        Process all scenes for a given taskid
        """
        tasks = self.get_tasks(task_id)
        
        if not tasks:
            print(f"No tasks found with taskid: {task_id}")
            return
            
        for task in tasks:
            scene_id = task.get('sceneid')
            nova_arn = task.get('nova-arn')
            polly_task = task.get('polly-task')
            
            video_status = 'NOT_STARTED'
            audio_status = 'NOT_STARTED'
            
            if nova_arn:
                video_status,video_uri = self.check_nova_status(nova_arn)
            
            if polly_task:
                audio_status = self.check_polly_status(polly_task)
            
            self.update_task_status(task_id, scene_id, video_status,  video_uri, audio_status)
            print(f"Updated task {task_id} scene {scene_id}: Video={video_status}, Audio={audio_status}")

def lambda_handler(event, context):
    task_id = event.get('taskId')
    
    if not task_id:
        raise ValueError("taskId is required in the event input")
    
    checker = TaskStatusChecker()
    tasks = checker.get_tasks(task_id)
    
    if not tasks:
        raise ValueError(f"No tasks found for taskId: {task_id}")
    
    for task in tasks:
        scene_id = task.get('sceneid')
        nova_arn = task.get('nova-arn')
        polly_task = task.get('polly-task')
        
        video_status = ''
        audio_status = ''
        video_uri = ''
        
        if nova_arn:
            video_status, video_uri = checker.check_nova_status(nova_arn)
        
        if polly_task:
            audio_status = checker.check_polly_status(polly_task)
        
        checker.update_task_status(task_id, scene_id, video_status, video_uri, audio_status)
        
    
    # Check task statuses
    has_in_progress = any(t.get('video_status') == 'InProgress' or t.get('audio_status') == 'inprogress' for t in tasks)
    has_failed = any(t.get('video_status') == 'Failed' or t.get('audio_status') == 'failed' for t in tasks)
    has_not_started = any(t.get('video_status') == 'NOT_STARTED' or t.get('audio_status') == 'NOT_STARTED' for t in tasks)
    all_completed = all((t.get('video_status') == 'Completed' and t.get('audio_status') == 'completed') for t in tasks)

    status = 'IN_PROGRESS'
    if all_completed:
        status = 'COMPLETED'
    elif not has_in_progress:
        if has_failed:
            status = 'FAILED'
        elif has_not_started:
            status = 'PARTIAL_COMPLETED'

    return {
            'taskId': task_id,
            'status': status
    }
