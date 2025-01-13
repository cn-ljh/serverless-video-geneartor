// Configure AWS SDK with credentials
AWS.config.update({
    region: 'us-east-1',
    credentials: new AWS.Credentials({
        accessKeyId: '',
        secretAccessKey: '',
        sessionToken: ''
    })
});

const s3 = new AWS.S3();

// Function to convert https S3 URL to s3:// format
function convertHttpsToS3Uri(httpsUrl) {
    try {
        const url = new URL(httpsUrl);
        if (url.hostname === 's3.us-east-1.amazonaws.com') {
            const bucket = url.pathname.split('/')[1];
            const key = url.pathname.substring(url.pathname.indexOf('/', 1) + 1);
            return `s3://${bucket}/${key}`;
        }
        return null;
    } catch (error) {
        console.error('Error converting HTTPS URL to S3 URI:', error);
        return null;
    }
}

// Function to generate presigned URL
async function getPresignedUrl(s3Uri) {
    if (!s3Uri) return null;
    
    try {
        // Parse S3 URI (s3://bucket-name/key)
        const matches = s3Uri.match(/^s3:\/\/([^\/]+)\/(.+)$/);
        if (!matches) return null;
        
        const [, bucket, key] = matches;
        
        const params = {
            Bucket: bucket,
            Key: key,
            Expires: 3600 // URL expires in 1 hour
        };
        
        return await new Promise((resolve, reject) => {
            s3.getSignedUrl('getObject', params, (err, url) => {
                if (err) reject(err);
                else resolve(url);
            });
        });
    } catch (error) {
        console.error('Error generating presigned URL:', error);
        return null;
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const apiEndpoint = 'https://owcnnmway4.execute-api.us-east-1.amazonaws.com/prod';
    const userInput = document.getElementById('userInput');
    const submitBtn = document.getElementById('submitBtn');
    const taskId = document.getElementById('taskId');
    const queryBtn = document.getElementById('queryBtn');
    const taskTable = document.getElementById('taskTable');
    const resultUrl = document.getElementById('resultUrl');
    const generateFinalBtn = document.getElementById('generateFinalBtn');

    // Add generate final video button event listener
    generateFinalBtn.addEventListener('click', async function(event) {
        event.preventDefault();
        if (!taskId.value.trim()) {
            alert('请先输入任务ID');
            return;
        }
        await generateFinalVideo();
    });

    // Add submit button event listener
    submitBtn.addEventListener('click', function(event) {
        event.preventDefault(); // Prevent form submission and page refresh
        submitTask();
    });
    
    // Add query button event listener
    queryBtn.addEventListener('click', function(event) {
        event.preventDefault(); // Prevent form submission and page refresh
        queryTask();
    });

    async function submitTask() {
        try {
            const response = await fetch(`${apiEndpoint}/parse`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    prompt: userInput.value
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Task submitted:', data);
            
            // Extract task ID from executionArn
            const taskId = data.executionArn.split(':').pop();
            
            // Display task ID in the UI
            document.getElementById('taskId').value = taskId;
            
            // Show success message with task ID
            alert(`任务提交成功！任务ID: ${taskId}`);
        } catch (error) {
            console.error('Error submitting task:', error);
            alert('Failed to submit task. Please try again.');
        }
    }

    async function queryTask() {
        if (!taskId.value.trim()) {
            alert('Please enter a task ID');
            return;
        }

        try {
            const response = await fetch(`${apiEndpoint}/query`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    taskId: taskId.value
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Task query result:', data);
            
            // Update UI with queried data
            updateUI(data);
        } catch (error) {
            console.error('Error querying task:', error);
            alert('Failed to query task. Please check the task ID and try again.');
        }
    }

    async function retryTask(sceneId, taskId, options = {}) {
        try {
            const payload = {
                taskId: taskId,
                sceneId: sceneId,
                ...options
            };

            const response = await fetch(`${apiEndpoint}/retry`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Task retried:', data);
            alert(`场景 ${sceneId} 重试请求提交成功！`);
            
            // Query task to update UI
            queryTask();
        } catch (error) {
            console.error('Error retrying task:', error);
            alert(`场景 ${sceneId} 重试失败：${error.message}`);
        }
    }

    async function updateUI(data) {
        if (!Array.isArray(data)) return;

        try {
            const tbody = taskTable.querySelector('tbody');
            tbody.innerHTML = ''; // Clear existing rows
            
            // Sort scenes by sceneid
            data.sort((a, b) => parseInt(a.sceneid) - parseInt(b.sceneid));
            
            // Process all scenes in parallel
            await Promise.all(data.map(async (scene) => {
                const audioStatus = scene.audio_status || 'pending';
                const imageStatus = scene.image_status || 'pending';
                const videoStatus = scene.video_status || 'pending';

                // Check if all statuses match the completion criteria
                const isAudioCompleted = audioStatus === 'completed';
                const isImageCompleted = imageStatus === 'SUCCESS';
                const isVideoCompleted = videoStatus === 'Completed';
                
                // Generate presigned URLs for S3 resources
                let audioUrl = null;
                let imageUrl = null;
                let videoUrl = null;
                
                if (isAudioCompleted && scene['polly-uri']) {
                    const audioS3Uri = convertHttpsToS3Uri(scene['polly-uri']);
                    if (audioS3Uri) {
                        audioUrl = await getPresignedUrl(audioS3Uri);
                    }
                }
                if (isImageCompleted && scene['image-uri']) {
                    imageUrl = await getPresignedUrl(scene['image-uri']);
                }
                if (isVideoCompleted && scene.video_uri) {
                    videoUrl = await getPresignedUrl(scene.video_uri);
                }

                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${scene.sceneid}</td>
                    <td>${scene.text || 'text'}</td>
                    <td>
                        ${isAudioCompleted && audioUrl ? 
                            `<a href="${audioUrl}" target="_blank">查看音频</a>` : 
                            audioStatus}
                        <div class="retry-option">
                            <input type="checkbox" class="retry-audio">
                            <label>重试</label>
                        </div>
                    </td>
                    <td>
                        ${isImageCompleted && imageUrl ? 
                            `<a href="${imageUrl}" target="_blank">查看图片</a>` : 
                            imageStatus}
                        <div class="retry-option">
                            <input type="checkbox" class="retry-image">
                            <label>重试</label>
                        </div>
                    </td>
                    <td>
                        ${isVideoCompleted && videoUrl ? 
                            `<a href="${videoUrl}" target="_blank">查看视频</a>` : 
                            videoStatus}
                        <div class="retry-option">
                            <input type="checkbox" class="retry-video">
                            <label>重试</label>
                        </div>
                    </td>
                    <td><button class="retry-btn">重试</button></td>
                `;
                tbody.appendChild(row);
            }));

            // Add event listeners to retry buttons
            tbody.querySelectorAll('.retry-btn').forEach(button => {
                button.addEventListener('click', function() {
                    const row = this.closest('tr');
                    const sceneId = row.cells[0].textContent;
                    const currentTaskId = document.getElementById('taskId').value;
                    
                    if (!currentTaskId) {
                        alert('Please enter a task ID');
                        return;
                    }

                    // Get checkbox states
                    const options = {
                        audio: row.querySelector('.retry-audio')?.checked || false,
                        image: row.querySelector('.retry-image')?.checked || false,
                        video: row.querySelector('.retry-video')?.checked || false
                    };

                    // Log selected options
                    console.log('Selected retry options:', options);
                    alert(`Selected options for scene ${sceneId}:\nAudio: ${options.audio}\nImage: ${options.image}\nVideo: ${options.video}`);

                    retryTask(sceneId, currentTaskId, options);
                });
            });

            // Handle final video URL from scene0's final_video
            const scene0 = data.find(scene => scene.sceneid === "0");
            if (scene0?.final_video) {
                const finalVideoUrl = await getPresignedUrl(scene0.final_video);
                resultUrl.innerHTML = finalVideoUrl ? 
                    `<a href="${finalVideoUrl}" target="_blank">点击下载最终视频</a>` : 
                    '暂无最终视频';
            } else {
                resultUrl.innerHTML = '暂无最终视频';
            }
        } catch (error) {
            console.error('Error updating UI:', error);
        }
    }

    async function generateFinalVideo() {
        try {
            const response = await fetch(`${apiEndpoint}/re-syntherizer`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    taskId: taskId.value
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            alert('已开始重新生成最终视频，请稍后查询状态');
            
            // Query task to update UI
            queryTask();
        } catch (error) {
            console.error('Error re-synthesizing video:', error);
            alert('重新生成视频失败，请重试');
        }
    }
});
