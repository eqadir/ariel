FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

RUN apt-get -y update && apt-get -y upgrade && \
  apt-get install -y --no-install-recommends ffmpeg && \
  DEBIAN_FRONTEND=noninteractive apt-get -y install tzdata curl python3-pip python3-dev python-is-python3

RUN curl https://dl.google.com/dl/cloudsdk/release/google-cloud-sdk.tar.gz > /tmp/google-cloud-sdk.tar.gz && \
  mkdir -p /usr/local/gcloud \
  && tar -C /usr/local/gcloud -xvf /tmp/google-cloud-sdk.tar.gz \
  && /usr/local/gcloud/google-cloud-sdk/install.sh
ENV PATH $PATH:/usr/local/gcloud/google-cloud-sdk/bin

ENV LD_LIBRARY_PATH /usr/local/nvidia/lib64:${LD_LIBRARY_PATH}

WORKDIR /ariel
COPY requirements.txt .
RUN pip install -r ./requirements.txt

COPY app.py .

ENV PORT 8080
CMD exec gunicorn -b 0.0.0.0:$PORT -t 600 -w 7 app:app
