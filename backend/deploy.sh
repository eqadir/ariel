#!/bin/bash
GCP_PROJECT_ID=$(gcloud config get project)
export GCS_BUCKET=$GCP_PROJECT_ID-ariel-us
export GCP_REGION=us-central1

gcloud config set project $GCP_PROJECT_ID
gcloud services enable cloudresourcemanager.googleapis.com
gcloud auth application-default set-quota-project $GCP_PROJECT_ID
printf "\nINFO - GCP project set to '$GCP_PROJECT_ID' succesfully!\n"

BUCKET_EXISTS=$(gcloud storage ls gs://$GCS_BUCKET > /dev/null 2>&1 && echo "true" || echo "false")
if "${BUCKET_EXISTS}"; then
  printf "\nWARN - Bucket '$GCS_BUCKET' already exists. Skipping bucket creation...\n"
else
  gcloud storage buckets create gs://$GCS_BUCKET --project=$GCP_PROJECT_ID --location=$GCP_REGION --uniform-bucket-level-access
  test $? -eq 0 || exit
  printf "\nINFO - Bucket '$GCS_BUCKET' created successfully in location '$GCP_REGION'!\n"
fi

printf "\nINFO - Enabling GCP APIs...\n"
gcloud services enable \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  cloudfunctions.googleapis.com \
  compute.googleapis.com \
  eventarc.googleapis.com \
  logging.googleapis.com \
  pubsub.googleapis.com \
  run.googleapis.com \
  script.googleapis.com \
  serviceusage.googleapis.com \
  storage.googleapis.com \
  videointelligence.googleapis.com

PROJECT_NUMBER=$(gcloud projects describe $GCP_PROJECT_ID --format="value(projectNumber)")
STORAGE_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com"
EVENTARC_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gcp-sa-eventarc.iam.gserviceaccount.com"
VERTEXAI_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com"
COMPUTE_SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
printf "\nINFO - Creating Service Agents and granting roles...\n"
for SA in "aiplatform.googleapis.com" "storage.googleapis.com" "eventarc.googleapis.com"; do
    gcloud --no-user-output-enabled beta services identity create --project=$GCP_PROJECT_ID \
        --service="${SA}"
done
COMPUTE_SA_ROLES=(
    "roles/eventarc.eventReceiver"
    "roles/run.invoker"
    "roles/cloudfunctions.invoker"
    "roles/storage.objectAdmin"
    "roles/aiplatform.user"
    "roles/logging.logWriter"
    "roles/artifactregistry.createOnPushWriter"
    "roles/cloudbuild.builds.builder"
)
for COMPUTE_SA_ROLE in "${COMPUTE_SA_ROLES[@]}"; do
    gcloud --no-user-output-enabled projects add-iam-policy-binding \
        $GCP_PROJECT_ID \
        --member="serviceAccount:${COMPUTE_SERVICE_ACCOUNT}" \
        --role="${COMPUTE_SA_ROLE}"
done
gcloud --no-user-output-enabled projects add-iam-policy-binding \
    $GCP_PROJECT_ID \
    --member="serviceAccount:${STORAGE_SERVICE_ACCOUNT}" \
    --role="roles/pubsub.publisher"
gcloud --no-user-output-enabled projects add-iam-policy-binding \
    $GCP_PROJECT_ID \
    --member="serviceAccount:${EVENTARC_SERVICE_ACCOUNT}" \
    --role="roles/eventarc.serviceAgent"
gcloud --no-user-output-enabled projects add-iam-policy-binding \
    $GCP_PROJECT_ID \
    --member="serviceAccount:${VERTEXAI_SERVICE_ACCOUNT}" \
    --role="roles/storage.objectViewer"
printf "Operation finished successfully!\n"
printf "\nINFO - Deploying the 'ariel-generate-utterances' Cloud Function...\n"

# gcloud beta run deploy ariel-generate-utterances \
#   --region=$GCP_REGION \
#   --function=generate_utterances \
#   --no-allow-unauthenticated \
#   --source=. \
#   --base-image=google-22-full/python312 \
#   --memory=16Gi \
#   --cpu=4 \
#   --gpu=1 \
#   --gpu-type=nvidia-l4 \
#   --max-instances=1 \
#   --timeout=120s

gcloud eventarc triggers create ariel-generate-utterances-trigger \
  --destination-run-service=ariel-generate-utterances \
  --destination-run-region=$GCP_REGION \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=$GCS_BUCKET" \
  --location="$GCP_REGION" \
  --service-account="$COMPUTE_SERVICE_ACCOUNT"


test $? -eq 0 || exit


