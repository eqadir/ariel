#!/bin/bash

# only REGIONs supported currently to us-central1 and asia-southeast1
GCP_PROJECT_ID=$(gcloud config get project)
GCP_REGION=us-central1
GCS_BUCKET=cse-kubarozek-sandbox-ariel
PROJECT_NUMBER=$(gcloud projects describe $GCP_PROJECT_ID --format="value(projectNumber)")
EVENTARC_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gcp-sa-eventarc.iam.gserviceaccount.com"
COMPUTE_SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud beta run deploy ariel-generate-utterances \
  --region=$GCP_REGION \
  --function=generate_utterances \
  --no-allow-unauthenticated \
  --source=. \
  --base-image=google-22-full/python312 \
  --memory=8Gi \
  --cpu=2 \
  --gpu=1 \
  --timeout=120s

# gcloud eventarc triggers create ariel-generate-utterances-trigger \
#   --destination-run-service=ariel-generate-utterances \
#   --destination-run-region=$GCP_REGION \
#   --event-filters="type=google.cloud.storage.object.v1.finalized" \
#   --event-filters="bucket=$GCS_BUCKET" \
#   --location="$GCP_REGION" \
#   --serviceAccount="$EVENTARC_SERVICE_ACCOUNT"
