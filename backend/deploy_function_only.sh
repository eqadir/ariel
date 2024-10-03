#!/bin/bash

# only REGIONs supported currently to us-central1 and asia-southeast1
GCP_PROJECT_ID=$(gcloud config get project)
GCP_REGION=us-central1
GCS_BUCKET=cse-kubarozek-sandbox-ariel-us
PROJECT_NUMBER=$(gcloud projects describe $GCP_PROJECT_ID --format="value(projectNumber)")
COMPUTE_SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

#build on cloud build
# gcloud beta run deploy ariel-process \
#   --region=$GCP_REGION \
#   --no-allow-unauthenticated \
#   --source=. \
#   --memory=32Gi \
#   --cpu=8 \
#   --gpu=1 \
#   --gpu-type=nvidia-l4 \
#   --max-instances=1 \
#   --timeout=600s

#ALT: build locally, push to artifact registry and deploy from there (As opposed to cloud build, maybe it'll be faster)
DOCKER_REPO_NAME=gps-docker-repo
echo **IGNORE the following error, if the repository already exists**
gcloud artifacts repositories create $DOCKER_REPO_NAME --repository-format=docker \
    --location=$GCP_REGION --description="Google Professional Services images" \
    --project=$GCP_PROJECT_ID

ARTIFACT_POSITORY_NAME=$GCP_REGION-docker.pkg.dev/$GCP_PROJECT_ID/$DOCKER_REPO_NAME

DOCKER_IMAGE_TAG=$ARTIFACT_POSITORY_NAME/ariel-process:latest
docker build -t $DOCKER_IMAGE_TAG .
docker push $DOCKER_IMAGE_TAG
gcloud beta run deploy ariel-process \
  --region=$GCP_REGION \
  --no-allow-unauthenticated \
  --image=$DOCKER_IMAGE_TAG \
  --memory=32Gi \
  --cpu=8 \
  --gpu=1 \
  --gpu-type=nvidia-l4 \
  --max-instances=1 \
  --timeout=600s

#anyway: setup trigger
# gcloud eventarc triggers create ariel-process-trigger \
#   --destination-run-service=ariel-process \
#   --destination-run-region=$GCP_REGION \
#   --event-filters="bucket=$GCS_BUCKET" \
#   --event-filters="type=google.cloud.storage.object.v1.finalized" \
#   --location="$GCP_REGION" \
#   --service-account="$COMPUTE_SERVICE_ACCOUNT"
