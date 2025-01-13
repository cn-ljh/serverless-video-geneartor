# Serverless Video Generation Pipeline

This project implements a serverless video generation pipeline using AWS services including Lambda, Step Functions, API Gateway, DynamoDB, and S3.

## Architecture

The solution uses:
- API Gateway for HTTP endpoints
- Step Functions for workflow orchestration
- Lambda functions for processing
- DynamoDB for data storage
- S3 for file storage
- Amazon Bedrock for AI/ML tasks
- Amazon Polly for text-to-speech

## Prerequisites

1. AWS CLI installed and configured
2. SAM CLI installed
3. Python 3.9
4. Docker (for building Lambda layers)
5. Amazon Bedrock access enabled in your AWS account
6. Amazon Polly access enabled in your AWS account

## Deployment Steps

To deploy the application:
```bash
# Make the script executable
chmod +x deploy.sh

# Run the deployment script
./deploy.sh
```

During the guided deployment, you'll need to:
- Enter a stack name
- Choose an AWS Region
- Confirm IAM role creation
- Allow SAM CLI to create named resources

After deployment, SAM will output:
- API Gateway endpoint URL
- Step Functions state machine ARN

## Testing the Pipeline

1. Send a POST request to the API endpoint:
```bash
curl -X POST https://your-api-endpoint/prod/parse \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Your text prompt here"}'
```

2. The response will include a taskId that you can use to track the progress:
```json
{
  "taskId": "123e4567-e89b-12d3-a456-426614174000"
}
```

3. Monitor the task status in the AWS Step Functions console.

## Architecture Components

### Lambda Functions

1. **Input Parser**
   - Processes incoming text prompts
   - Uses Amazon Bedrock for text analysis
   - Stores results in DynamoDB

2. **Create Task**
   - Initializes task processing
   - Creates task records in DynamoDB

3. **Image Generator**
   - Uses Amazon Bedrock for image generation
   - Stores images in S3

4. **Speech Generator**
   - Uses Amazon Polly for text-to-speech
   - Stores audio files in S3

5. **Video Generator**
   - Uses Amazon Bedrock for video generation
   - Processes images from S3

6. **Task Status Checker**
   - Monitors task progress
   - Updates task status in DynamoDB

7. **Video Synthesizer**
   - Combines video and audio
   - Creates final output

### Storage

1. **DynamoDB Table**
   - Stores task and scene information
   - Partition key: taskid
   - Sort key: sceneid

2. **S3 Bucket**
   - Stores generated media files
   - Organized by task ID and media type

## Security

The deployment includes:
- IAM roles with least privilege access
- API Gateway with CORS configuration
- S3 bucket policies
- DynamoDB access controls

## Cleanup

To remove all deployed resources:
```bash
sam delete
```

## Troubleshooting

1. Check CloudWatch Logs for each Lambda function
2. Monitor Step Functions execution history
3. Verify DynamoDB items and S3 objects
4. Check IAM roles and permissions

## Limitations

1. Maximum video duration: 6 seconds per scene
2. File size limits:
   - Lambda payload: 6 MB
   - API Gateway: 10 MB
3. Processing time varies based on complexity
