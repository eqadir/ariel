#!/bin/bash

# only REGIONs supported currently to us-central1 and asia-southeast1
GCP_PROJECT_ID=$(gcloud config get project)
GCP_REGION=us-central1
GCS_BUCKET=cse-kubarozek-sandbox-ariel-us
PROJECT_NUMBER=$(gcloud projects describe $GCP_PROJECT_ID --format="value(projectNumber)")
COMPUTE_SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"



gcloud beta run deploy ariel-process \
  --region=$GCP_REGION \
  --no-allow-unauthenticated \
  --source=. \
  --memory=32Gi \
  --cpu=8 \
  --gpu=1 \
  --gpu-type=nvidia-l4 \
  --max-instances=1 \
  --timeout=600s

gcloud eventarc triggers create ariel-process-trigger \
  --destination-run-service=ariel-process \
  --destination-run-region=$GCP_REGION \
  --event-filters="bucket=cse-kubarozek-sandbox-ariel-us" \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --location="$GCP_REGION" \
  --service-account="$COMPUTE_SERVICE_ACCOUNT"
