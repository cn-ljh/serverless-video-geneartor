# Use an official Python 3.9 runtime as a parent image
FROM public.ecr.aws/lambda/python:3.9

# Set up working directory
WORKDIR /var/task

# Install required tools and dependencies
RUN yum install -y tar xz wget freetype freetype-devel fontconfig fontconfig-devel

# Upgrade pip
RUN pip install --upgrade pip

# Download and install static FFmpeg build with all filters
RUN mkdir -p /var/task/ffmpeg && \
    cd /var/task/ffmpeg && \
    wget https://www.johnvansickle.com/ffmpeg/old-releases/ffmpeg-4.4.1-amd64-static.tar.xz && \
    tar xf ffmpeg-4.4.1-amd64-static.tar.xz && \
    mv ffmpeg-4.4.1-amd64-static/ffmpeg . && \
    mv ffmpeg-4.4.1-amd64-static/ffprobe . && \
    rm -rf ffmpeg-4.4.1-amd64-static* && \
    chmod +x ffmpeg ffprobe && \
    ./ffmpeg -version

# Add ffmpeg to PATH
ENV PATH="/var/task/ffmpeg:${PATH}"

# Verify FFmpeg has drawtext filter
RUN /var/task/ffmpeg/ffmpeg -filters 2>&1 | grep -q drawtext || (echo "FFmpeg drawtext filter not available" && exit 1)

# Copy function code
COPY . ${LAMBDA_TASK_ROOT}


# Install Python dependencies
RUN pip install -r requirements.txt -t /var/task

# Set up fonts
RUN mkdir -p /var/task/fonts /usr/share/fonts/truetype
COPY ["./fonts/Arial.ttf", "/var/task/fonts/"]
COPY ["./fonts/Arial.ttf", "/usr/share/fonts/truetype/"]
COPY ["./fonts/Arial Unicode.ttf", "/var/task/fonts/"]
COPY ["./fonts/Arial Unicode.ttf", "/usr/share/fonts/truetype/"]
COPY fonts/fonts.conf /var/task/fonts/
ENV FONTCONFIG_FILE=/var/task/fonts/fonts.conf
RUN chmod -R 755 /var/task/fonts /usr/share/fonts/truetype && \
    fc-cache -f -v

# Set the CMD to your handler
CMD [ "video_synthesizer.lambda_handler" ]
