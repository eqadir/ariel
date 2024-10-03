#!/bin/bash
docker build -t gtech/ariel .
#run cloud-run ready docker packaged instance on port 8888
docker run -it \
-p 8888:8888 \
-e PORT=8888 \
-e GOOGLE_APPLICATION_CREDENTIALS=/tmp/keys/FILE_NAME.json \
-v $GOOGLE_APPLICATION_CREDENTIALS:/tmp/keys/FILE_NAME.json:ro \
-e GOOGLE_CLOUD_PROJECT="$(gcloud config get project)" \
 gtech/ariel
