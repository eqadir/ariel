FROM nvidia/cuda:12.6.1-base-ubuntu24.04

RUN apt-get -y update && apt-get -y upgrade
RUN apt-get install -y --no-install-recommends ffmpeg
RUN DEBIAN_FRONTEND=noninteractive apt-get -y install tzdata
RUN apt-get install -y python3-pip python3-dev python-is-python3 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /ariel

COPY requirements.txt .
RUN pip install -r ./requirements.txt --break-system-packages

COPY app.py .

# Service must listen to $PORT environment variable.
# This default value facilitates local development.
ENV PORT 8080

# Run the web service on container startup.
CMD exec gunicorn -b 0.0.0.0:$PORT -t 600 -w 7 app:app
