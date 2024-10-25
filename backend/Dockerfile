FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

# RUN apt-get -y update
# RUN apt-get -y upgrade
# RUN apt-get install -y curl
# CUDA image should already have python
RUN apt-get update && \
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pip python3-dev python-is-python3 curl tzdata ffmpeg && \
  rm -rf /var/lib/apt/lists/*
# RUN DEBIAN_FRONTEND=noninteractive apt-get -y install tzdata
# RUN apt-get install -y --no-install-recommends ffmpeg

#install gcloud
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
  curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
  apt-get update -y && apt-get install google-cloud-cli -y && rm -rf /var/lib/apt/lists/*

# RUN curl https://dl.google.com/dl/cloudsdk/release/google-cloud-sdk.tar.gz > /tmp/google-cloud-sdk.tar.gz && \
#   mkdir -p /usr/local/gcloud \
#   && tar -C /usr/local/gcloud -xvf /tmp/google-cloud-sdk.tar.gz \
#   && /usr/local/gcloud/google-cloud-sdk/install.sh
# ENV PATH $PATH:/usr/local/gcloud/google-cloud-sdk/bin


WORKDIR /ariel
COPY requirements.txt .
RUN pip install -r ./requirements.txt

COPY app.py .

ENV PORT 8080
CMD exec gunicorn -b 0.0.0.0:$PORT -t 600 -w 7 app:app




# RUN apt-get -y update && apt-get -y upgrade
# RUN apt-get install -y --no-install-recommends ffmpeg
# RUN DEBIAN_FRONTEND=noninteractive apt-get -y install tzdata
# RUN apt-get install -y python3-pip python3-dev python-is-python3 && \
#     rm -rf /var/lib/apt/lists/*

# WORKDIR /ariel

# COPY requirements.txt .
# RUN pip install -r ./requirements.txt --break-system-packages

# COPY app.py .

# # Service must listen to $PORT environment variable.
# # This default value facilitates local development.
# ENV PORT 8080

# # Run the web service on container startup.
# CMD exec gunicorn -b 0.0.0.0:$PORT -t 600 -w 7 app:app
