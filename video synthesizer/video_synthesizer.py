import boto3
import os
import subprocess
from urllib.parse import urlparse
import tempfile
import re
import json

class VideoSynthesizer:
    def __init__(self):
        self.s3 = boto3.client('s3')
        
        # Check ffmpeg and ffprobe availability
        try:
            version_cmd = ['ffmpeg', '-version']
            result = subprocess.run(version_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError("ffmpeg is not available")
            print("ffmpeg version check passed")
            
            probe_cmd = ['ffprobe', '-version']
            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError("ffprobe is not available")
            print("ffprobe version check passed")
        except Exception as e:
            raise RuntimeError(f"Failed to verify ffmpeg/ffprobe installation: {str(e)}")
            
        # Create temp directory with full permissions
        self.temp_dir = tempfile.mkdtemp(prefix='video_synth_')
        os.chmod(self.temp_dir, 0o777)
        print(f"Created temporary directory: {self.temp_dir}")

    def get_items_by_taskid(self, taskid):
        """Query DynamoDB table for items with given taskid"""
        # Initialize DynamoDB with region
        dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
        
        response = table.query(
            KeyConditionExpression='taskid = :tid',
            ExpressionAttributeValues={':tid': taskid}
        )
        # Sort items by sceneid
        items = sorted(response['Items'], key=lambda x: int(x.get('sceneid', 0)))
        return items

    def validate_video_uri(self, uri):
        """Validate video URI format (s3://bucket/key)"""
        if not uri:
            return False
        try:
            parsed = urlparse(uri)
            return parsed.scheme == 's3'
        except:
            return False

    def validate_polly_uri(self, uri):
        """Validate Polly URI format (https://s3.*.amazonaws.com/bucket/key)"""
        if not uri:
            return False
        try:
            parsed = urlparse(uri)
            return (parsed.scheme == 'https' and 
                   's3.' in parsed.netloc and 
                   'amazonaws.com' in parsed.netloc)
        except:
            return False

    def check_s3_file_exists(self, bucket, key):
        """Check if file exists in S3"""
        try:
            self.s3.head_object(Bucket=bucket, Key=key)
            return True
        except:
            return False

    def parse_s3_uri(self, uri):
        """Parse S3 URI into bucket and key"""
        parsed = urlparse(uri)
        if parsed.scheme == 's3':
            # Handle s3:// format
            bucket = parsed.netloc
            key = parsed.path.lstrip('/')
            return bucket, key
        elif parsed.scheme == 'https' and 'amazonaws.com' in parsed.netloc:
            # Handle https://s3.region.amazonaws.com/bucket/key format
            # or https://bucket.s3.region.amazonaws.com/key format
            path = parsed.path.lstrip('/')
            if parsed.netloc.startswith('s3.'):
                # Format: s3.region.amazonaws.com/bucket/key
                parts = path.split('/', 1)
                if len(parts) != 2:
                    raise ValueError(f"Invalid S3 HTTPS URI format: {uri}")
                bucket = parts[0]
                key = parts[1]
            else:
                # Format: bucket.s3.region.amazonaws.com/key
                bucket = parsed.netloc.split('.s3.')[0]
                key = path

            return bucket, key
        raise ValueError(f"Invalid S3 URI format: {uri}")

    def download_file(self, uri, local_filename):
        """Download file from S3 to local storage"""
        bucket, key = self.parse_s3_uri(uri)
        local_path = os.path.join(self.temp_dir, local_filename)
        self.s3.download_file(bucket, key, local_path)
        # Ensure file has proper permissions
        os.chmod(local_path, 0o666)
        print(f"Downloaded and set permissions for: {local_path}")
        return local_path

    def run_ffmpeg_command(self, command, ignore_errors=False):
        """Execute ffmpeg command"""
        try:
            print(f"Executing command: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True)
            if result.stdout:
                print(f"FFmpeg stdout: {result.stdout}")
            if result.stderr:
                print(f"FFmpeg stderr: {result.stderr}")
            if not ignore_errors and result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, command, 
                    output=result.stdout, 
                    stderr=result.stderr
                )
            return result
        except subprocess.CalledProcessError as e:
            if not ignore_errors:
                print(f"FFmpeg error: {e.stderr}")
                raise
            return e

    def synthesize_video(self, taskid, output_filename='output_combined.mp4'):
        """Main function to synthesize video and audio"""
        # Ensure output path is in temp directory
        output_path = os.path.join(self.temp_dir, output_filename)
        try:
            # Get items from DynamoDB
            items = self.get_items_by_taskid(taskid)
            if not items:
                raise ValueError(f"No items found for taskid: {taskid}")

            # Create a file to store the list of videos for concatenation
            concat_file = os.path.join(self.temp_dir, 'file_list.txt')
            processed_videos = []
            
            # Process each scene
            for i, item in enumerate(items):
                video_uri = item.get('video_uri')
                polly_uri = item.get('polly-uri')
                scene_id = item.get('sceneid', str(i))
                print(f"Processing scene {scene_id}")
                print(f"Video URI: {video_uri}")
                print(f"Audio URI: {polly_uri}")
                
                # Validate URI formats
                if not self.validate_video_uri(video_uri):
                    print(f"Skipping scene {scene_id}: Invalid video URI format: {video_uri}")
                    continue
                    
                if not self.validate_polly_uri(polly_uri):
                    print(f"Skipping scene {scene_id}: Invalid Polly URI format: {polly_uri}")
                    continue

                try:
                    # Check if files exist in S3
                    video_bucket, video_key = self.parse_s3_uri(video_uri)
                    polly_bucket, polly_key = self.parse_s3_uri(polly_uri)

                    if not self.check_s3_file_exists(video_bucket, video_key):
                        print(f"Skipping scene {scene_id}: Video file not found in S3: {video_uri}")
                        continue

                    if not self.check_s3_file_exists(polly_bucket, polly_key):
                        print(f"Skipping scene {scene_id}: Audio file not found in S3: {polly_uri}")
                        continue

                    # Download files
                    video_path = self.download_file(video_uri, f'video_{i}.mp4')
                    audio_path = self.download_file(polly_uri, f'audio_{i}.mp3')
                    print(f"Downloaded video: {video_path}")
                    print(f"Downloaded audio: {audio_path}")
                except Exception as e:
                    print(f"Error processing scene {scene_id}: {str(e)}")
                    continue

                # Output path for the video with combined audio
                combined_path = os.path.join(self.temp_dir, f'combined_{i}.mp4')

                # Get text content for the scene
                # if scene_id=='0':
                #     text_content = item.get('text')
                # else:
                #     text_content = item.get('text', '')
                
                text_content = item.get('text', '')
                # Escape special characters for ffmpeg drawtext filter
                escaped_text = text_content.replace("'", "'\\''").replace(':', '\\:').replace('=', '\\=')
                
                # Check font paths
                font_paths = [
                    '/var/task/fonts/Arial Unicode.ttf',
                    '/usr/share/fonts/truetype/Arial Unicode.ttf'
                ]
                font_file = None
                for path in font_paths:
                    if os.path.exists(path):
                        font_file = path
                        print(f"Using font file: {font_file}")
                        break
                
                if not font_file:
                    raise RuntimeError("Arial Unicode.ttf font file not found in any of the expected locations")
                
                # Get durations of video and audio
                def get_duration(file_path):
                    cmd = [
                        'ffprobe', '-v', 'error',
                        '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1',
                        file_path
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    return float(result.stdout.strip())

                video_duration = get_duration(video_path)
                audio_duration = get_duration(audio_path)
                duration = min(video_duration, audio_duration)

                # Convert and combine video with audio and text overlay
                print(f"Processing video, audio, and text overlay for scene {scene_id}")
                print(f"{video_path}-video_duration:{video_duration},{audio_path}-audio_duration:{audio_duration}")
                command = [
                    'ffmpeg', '-y',
                    '-i', video_path,
                    '-f', 'mp3',  # Explicitly specify input format
                    '-i', audio_path,
                    '-t', str(duration),  # Limit duration to shorter input
                    '-vf', f"drawtext=fontfile={font_file}:text='{escaped_text}':fontsize=40:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=5:x=(w-text_w)/2:y=h-th-20",
                    '-c:a', 'aac',
                    '-strict', 'experimental',
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    '-shortest',
                    combined_path
                ]
                self.run_ffmpeg_command(command)
                
                # Verify the combined file exists and has both streams
                if not os.path.exists(combined_path):
                    print(f"Warning: Combined file not created for scene {scene_id}")
                    continue

                # Check file streams
                verify_command = [
                    'ffmpeg',
                    # '-loglevel', 'error',  # Only show errors
                    '-i', combined_path,
                    '-f', 'null',
                    '-'  # Output to null
                ]
                verify_result = self.run_ffmpeg_command(verify_command, ignore_errors=True)
                if verify_result.returncode != 0:
                    print(f"Warning: Combined file verification failed for scene {scene_id}")
                    continue

                # Check if file has video and audio streams
                probe_command = [
                    'ffprobe', '-v', 'error',
                    '-show_entries', 'stream=codec_type',
                    '-of', 'default=noprint_wrappers=1',
                    combined_path
                ]
                try:
                    probe_result = subprocess.run(probe_command, capture_output=True, text=True)
                    streams = probe_result.stdout.strip().split('\n')
                    has_video = 'codec_type=video' in streams
                    has_audio = 'codec_type=audio' in streams
                    
                    if not (has_video and has_audio):
                        print(f"Warning: Missing streams in scene {scene_id} - Video: {has_video}, Audio: {has_audio}")
                        continue
                except Exception as e:
                    print(f"Warning: Could not probe streams for scene {scene_id}: {str(e)}")
                    continue
                
                # Upload combined scene video to S3
                s3_bucket = video_bucket
                scene_s3_key = f'combined/{taskid}/{scene_id}_combined.mp4'
                self.s3.upload_file(combined_path, s3_bucket, scene_s3_key)
                combined_video_uri = f's3://{s3_bucket}/{scene_s3_key}'
                print(f"Uploaded combined scene video to: {combined_video_uri}")
                
                # Update DynamoDB with combined video URI
                dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
                table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
                
                table.update_item(
                    Key={
                        'taskid': taskid,
                        'sceneid': scene_id
                    },
                    UpdateExpression='SET combine_video_uri = :uri',
                    ExpressionAttributeValues={
                        ':uri': combined_video_uri
                    }
                )
                print(f"Updated DynamoDB with combined video URI for scene {scene_id}")
                
                processed_videos.append(combined_path)
                print(f"Successfully processed scene {scene_id}")

            # After all scenes are processed, concatenate the videos
            if processed_videos:
                print("Verifying video streams before concatenation...")
                valid_videos = []
                
                for video in processed_videos:
                    if not os.path.exists(video):
                        print(f"Warning: Video file does not exist: {video}")
                        continue
                    if not os.access(video, os.R_OK):
                        print(f"Warning: Video file is not readable: {video}")
                        continue
                        
                    # Verify video streams
                    probe_command = [
                        'ffprobe', '-v', 'error',
                        '-select_streams', 'v:0',  # Select first video stream
                        '-show_entries', 'stream=codec_name',
                        '-of', 'default=noprint_wrappers=1',
                        video
                    ]
                    try:
                        probe_result = subprocess.run(probe_command, capture_output=True, text=True)
                        if probe_result.returncode == 0 and 'codec_name=h264' in probe_result.stdout:
                            valid_videos.append(video)
                            print(f"Verified video streams in: {video}")
                        else:
                            print(f"Warning: Invalid video streams in: {video}")
                    except Exception as e:
                        print(f"Error verifying video: {video} - {str(e)}")
                        continue
                
                if not valid_videos:
                    raise ValueError("No valid videos to concatenate")
                
                print("Creating concat file with verified videos:")
                with open(concat_file, 'w') as f:
                    for video in valid_videos:
                        print(f"Adding to concat: {video}")
                        f.write(f"file '{video}'\n")
                
                with open(concat_file, 'r') as f:
                    content = f.read()
                    print(f"Concat file content:\n{content}")
                
                # Ensure output directory exists
                output_dir = os.path.dirname(os.path.abspath(output_path))
                os.makedirs(output_dir, exist_ok=True)
                
                # Concatenate videos
                command = [
                    'ffmpeg', '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-c', 'copy',        # Copy both video and audio streams
                    '-strict', 'experimental',
                    '-preset', 'medium', # Balance between encoding speed and quality
                    '-crf', '23',       # Constant Rate Factor for video quality (lower = better)
                    output_path
                ]
                try:
                    self.run_ffmpeg_command(command)
                except subprocess.CalledProcessError as e:
                    print(f"FFmpeg concatenation failed with return code {e.returncode}")
                    print(f"Command output: {e.output}")
                    print(f"Command stderr: {e.stderr}")
                    raise

                # Verify final output file exists and has correct streams
                if not os.path.exists(output_path):
                    raise ValueError(f"Final output file was not created: {output_path}")

                # Check final output streams
                probe_command = [
                    'ffprobe', '-v', 'error',
                    '-show_entries', 'stream=codec_type,codec_name',
                    '-of', 'default=noprint_wrappers=1',
                    output_path
                ]
                probe_result = subprocess.run(probe_command, capture_output=True, text=True)
                if probe_result.returncode != 0:
                    raise ValueError(f"Failed to probe final output file: {output_path}")

                # streams = probe_result.stdout.strip().split('\n')
                # has_video = any('codec_type=video' in s and 'codec_name=h264' in s for s in streams)
                # has_audio = any('codec_type=audio' in s and 'codec_name=aac' in s for s in streams)

                # if not (has_video and has_audio):
                #     raise ValueError(f"Final output missing required streams - Video(h264): {has_video}, Audio(aac): {has_audio}")

                # print(f"Video synthesis completed. Output saved to: {output_path}")
                
                # Upload final video to S3
                s3_bucket = video_bucket  # Use the bucket from the last processed video
                s3_key = f'final/{taskid}/{output_filename}'
                self.s3.upload_file(output_path, s3_bucket, s3_key)
                final_video_uri = f's3://{s3_bucket}/{s3_key}'
                print(f"Uploaded final video to: {final_video_uri}")
                
                # Update DynamoDB with final video URI
                dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
                table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])
                
                # Update the first item (scene 0) with the final video URI
                table.update_item(
                    Key={
                        'taskid': taskid,
                        'sceneid': '0'
                    },
                    UpdateExpression='SET final_video = :uri',
                    ExpressionAttributeValues={
                        ':uri': final_video_uri
                    }
                )
                print(f"Updated DynamoDB with final video URI")
                
            else:
                raise ValueError("No valid scenes to process")

        except Exception as e:
            print(f"Error during video synthesis: {str(e)}")
            raise
        finally:
            # Cleanup temporary files
            for file in os.listdir(self.temp_dir):
                try:
                    if file.endswith(('.mp4', '.mp3', '.srt', '.txt')):
                        os.remove(os.path.join(self.temp_dir, file))
                except Exception as e:
                    print(f"Error cleaning up file {file}: {str(e)}")
            try:
                os.rmdir(self.temp_dir)
            except:
                pass

def lambda_handler(event, context):
    """AWS Lambda handler function"""
    try:
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        }
        
        # Handle OPTIONS request
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': ''
            }
        # Handle API Gateway invocation
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
            taskid = body.get('taskId')
            output_filename = body.get('output', 'output_combined.mp4')
        else:
            # Direct lambda invocation
            taskid = event.get('taskId')
            output_filename = event.get('output', 'output_combined.mp4')
        
        if not taskid:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'taskId is required in the request body'})
            }
            
        synthesizer = VideoSynthesizer()
        synthesizer.synthesize_video(taskid, output_filename)
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'message': f'Video synthesis completed successfully. Output: {output_filename}'})
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': f'Error during video synthesis: {str(e)}'})
        }

if __name__ == '__main__':
    # For local testing
    test_event = {
        'taskid': 'a5c2b2d4-b275-4bf8-9dd0-c314413b00e3',
        'output': 'dengguanquelou-cn.mp4'
    }
    print(lambda_handler(test_event, None))
