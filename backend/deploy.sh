#!/bin/bash
GCP_PROJECT_ID=$(gcloud config get project)
export GCS_BUCKET=$GCP_PROJECT_ID-ariel-us
export GCP_REGION=us-central1

gcloud config set project $GCP_PROJECT_ID
gcloud services enable cloudresourcemanager.googleapis.com
gcloud auth application-default set-quota-project $GCP_PROJECT_ID
printf "\nINFO - GCP project set to '$GCP_PROJECT_ID' succesfully!\n"

# BUCKET_EXISTS=$(gcloud storage ls gs://$GCS_BUCKET > /dev/null 2>&1 && echo "true" || echo "false")
# if "${BUCKET_EXISTS}"; then
#   printf "\nWARN - Bucket '$GCS_BUCKET' already exists. Skipping bucket creation...\n"
# else
#   gcloud storage buckets create gs://$GCS_BUCKET --project=$GCP_PROJECT_ID --location=$GCP_REGION --uniform-bucket-level-access
#   test $? -eq 0 || exit
#   printf "\nINFO - Bucket '$GCS_BUCKET' created successfully in location '$GCP_REGION'!\n"
# fi

# printf "\nINFO - Enabling GCP APIs...\n"
# gcloud services enable \
#   artifactregistry.googleapis.com \
#   cloudbuild.googleapis.com \
#   compute.googleapis.com \
#   eventarc.googleapis.com \
#   logging.googleapis.com \
#   pubsub.googleapis.com \
#   run.googleapis.com \
#   script.googleapis.com \
#   serviceusage.googleapis.com \
#   storage.googleapis.com

# PROJECT_NUMBER=$(gcloud projects describe $GCP_PROJECT_ID --format="value(projectNumber)")
# STORAGE_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com"
# EVENTARC_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gcp-sa-eventarc.iam.gserviceaccount.com"
# COMPUTE_SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
# printf "\nINFO - Creating Service Agents and granting roles...\n"
# for SA in "aiplatform.googleapis.com" "storage.googleapis.com" "eventarc.googleapis.com"; do
#     gcloud --no-user-output-enabled beta services identity create --project=$GCP_PROJECT_ID \
#         --service="${SA}"
# done
# COMPUTE_SA_ROLES=(
#     "roles/eventarc.eventReceiver"
#     "roles/run.invoker"
#     "roles/cloudfunctions.invoker"
#     "roles/storage.objectAdmin"
#     "roles/aiplatform.user"
#     "roles/logging.logWriter"
#     "roles/artifactregistry.createOnPushWriter"
#     "roles/cloudbuild.builds.builder"
# )
# for COMPUTE_SA_ROLE in "${COMPUTE_SA_ROLES[@]}"; do
#     gcloud --no-user-output-enabled projects add-iam-policy-binding \
#         $GCP_PROJECT_ID \
#         --member="serviceAccount:${COMPUTE_SERVICE_ACCOUNT}" \
#         --role="${COMPUTE_SA_ROLE}"
# done
# gcloud --no-user-output-enabled projects add-iam-policy-binding \
#     $GCP_PROJECT_ID \
#     --member="serviceAccount:${STORAGE_SERVICE_ACCOUNT}" \
#     --role="roles/pubsub.publisher"
# gcloud --no-user-output-enabled projects add-iam-policy-binding \
#     $GCP_PROJECT_ID \
#     --member="serviceAccount:${EVENTARC_SERVICE_ACCOUNT}" \
#     --role="roles/eventarc.serviceAgent"
# printf "Operation finished successfully!\n"

DOCKER_REPO_NAME=gps-docker-repo
REPO_EXISTS=$(gcloud artifacts repositories describe $DOCKER_REPO_NAME --location=$GCP_REGION > /dev/null 2>&1 && echo "true" || echo "false")
if "${REPO_EXISTS}"; then
  printf "\nWARN - Repository '$DOCKER_REPO_NAME' already exists in location '$GCP_REGION'. Skipping creation...\n"
else
  printf "\nINFO Creating artifacts repository for docker images"
  gcloud artifacts repositories create $DOCKER_REPO_NAME --repository-format=docker \
      --location=$GCP_REGION --description="Google Professional Services images" \
      --project=$GCP_PROJECT_ID
  test $? -eq 0 || exit
  printf "\nINFO - Repository '$DOCKER_REPO_NAME' created successfully in location '$GCP_REGION'!\n"
fi

ARTIFACT_POSITORY_NAME=$GCP_REGION-docker.pkg.dev/$GCP_PROJECT_ID/$DOCKER_REPO_NAME

printf "\nINFO Building Docker image for ariel processor"
DOCKER_IMAGE_TAG=$ARTIFACT_POSITORY_NAME/ariel-process:latest
docker build -t $DOCKER_IMAGE_TAG .
docker push $DOCKER_IMAGE_TAG

printf "\nINFO - Deploying the 'ariel-process' Cloud Run container...\n"
gcloud beta run deploy ariel-process \
  --region=$GCP_REGION \
  --no-allow-unauthenticated \
  --image=$DOCKER_IMAGE_TAG \
  --memory=32Gi \
  --cpu=8 \
  --gpu=1 \
  --gpu-type=nvidia-l4 \
  --max-instances=1 \
  --timeout=600s \
  --concurrency=1

printf "\nINFO Setting up triggers from GCS to Ariel processor topic in Cloud Run"
gcloud eventarc triggers create ariel-bucket-trigger \
  --destination-run-service=ariel-process \
  --destination-run-region=$GCP_REGION \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="serviceName=storage.googleapis.com" \
  --event-filters="bucket=$GCS_BUCKET" \
  --location="$GCP_REGION" \
  --service-account="$COMPUTE_SERVICE_ACCOUNT"

printf "\nINFO Creating pub/sub topic and linking it back to processor"
gcloud pubsub topics create ariel-topic

SERVICE_URL=$(gcloud run services describe ariel-process --region $GCP_REGION --format='value(status.url)')

gcloud pubsub subscriptions create ariel-process-subscription --topic ariel-topic \
  --ack-deadline=600 \
  --push-endpoint=$SERVICE_URL/
  --push-auth-service-account="$COMPUTE_SERVICE_ACCOUNT"

# gcloud eventarc triggers create my-trigger --event-filters="type=google.cloud.pubsub.topic.v1.messagePublished" --destination-run-service=my-service

test $? -eq 0 || exit


