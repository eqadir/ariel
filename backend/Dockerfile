FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

RUN apt-get -y update && apt-get -y upgrade
RUN apt-get install -y --no-install-recommends ffmpeg
RUN DEBIAN_FRONTEND=noninteractive apt-get -y install tzdata
RUN apt-get install -y python3-pip python3-dev python-is-python3 && \
    rm -rf /var/lib/apt/lists/*

RUN apt-get -y update && apt-get install -y curl
RUN curl https://dl.google.com/dl/cloudsdk/release/google-cloud-sdk.tar.gz > /tmp/google-cloud-sdk.tar.gz
RUN mkdir -p /usr/local/gcloud \
  && tar -C /usr/local/gcloud -xvf /tmp/google-cloud-sdk.tar.gz \
  && /usr/local/gcloud/google-cloud-sdk/install.sh
ENV PATH $PATH:/usr/local/gcloud/google-cloud-sdk/bin

WORKDIR /ariel
COPY requirements.txt .
RUN pip install -r ./requirements.txt

COPY app.py .

ENV PORT 8080
CMD exec gunicorn -b 0.0.0.0:$PORT -t 600 -w 7 app:app
