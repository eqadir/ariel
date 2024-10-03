#!/bin/bash
GCP_REGION=us-central1
gcloud eventarc triggers delete ariel-config-trigger --location="$GCP_REGION"
gcloud eventarc triggers delete ariel-approved-trigger --location="$GCP_REGION"
