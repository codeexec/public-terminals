#!/bin/bash
#
# Create GKE Autopilot cluster for Terminal Server
#
# This script creates a GKE Autopilot cluster with:
# - Image streaming (automatic on Autopilot for fast container startup)
# - GPU support enabled
# - Workload Identity for secure service account access
# - Artifact Registry access for container images
#
# Prerequisites:
# - gcloud CLI installed and authenticated
# - Sufficient GPU quota in the target region
# - Container File System API enabled (for image streaming)
#
# Usage:
#   ./create-gke-cluster.sh
#
# Environment variables (optional):
#   GCP_PROJECT_ID    - GCP project ID (default: current gcloud project)
#   GCP_REGION        - GCP region (default: us-central1)
#   CLUSTER_NAME      - Cluster name (default: terminals-cluster)
#   K8S_NAMESPACE     - Kubernetes namespace (default: terminals)

set -euo pipefail

# Configuration with defaults
PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
CLUSTER_NAME="${CLUSTER_NAME:-terminals-cluster}"
NAMESPACE="${K8S_NAMESPACE:-terminals}"

if [ -z "$PROJECT_ID" ]; then
    echo "Error: GCP_PROJECT_ID not set and no default project configured"
    echo "Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "=== GKE Autopilot Cluster Setup ==="
echo "Project:   $PROJECT_ID"
echo "Region:    $REGION"
echo "Cluster:   $CLUSTER_NAME"
echo "Namespace: $NAMESPACE"
echo ""

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable container.googleapis.com \
    containerfilesystem.googleapis.com \
    artifactregistry.googleapis.com \
    --project="$PROJECT_ID"

# Check if cluster already exists
if gcloud container clusters describe "$CLUSTER_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" &>/dev/null; then
    echo "Cluster '$CLUSTER_NAME' already exists in region '$REGION'"
    echo "Skipping cluster creation..."
else
    echo "Creating GKE Autopilot cluster..."
    # Note: Workload Identity is enabled by default on Autopilot clusters
    gcloud container clusters create-auto "$CLUSTER_NAME" \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --release-channel=regular

    echo "Cluster created successfully!"
fi

# Get cluster credentials
echo "Getting cluster credentials..."
gcloud container clusters get-credentials "$CLUSTER_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID"

# Create namespace if it doesn't exist
echo "Creating namespace '$NAMESPACE'..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Create service account for terminal pods
echo "Creating service account..."
kubectl create serviceaccount terminal-server \
    --namespace="$NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -

# Display cluster info
echo ""
echo "=== Cluster Ready ==="
echo ""
echo "Cluster endpoint:"
kubectl cluster-info | head -1

echo ""
echo "Nodes (will auto-scale based on workload):"
kubectl get nodes 2>/dev/null || echo "No nodes yet (Autopilot scales on demand)"

echo ""
echo "=== Configuration for Terminal Server ==="
echo ""
echo "Add these environment variables to your deployment:"
echo ""
echo "  CONTAINER_PLATFORM=kubernetes"
echo "  K8S_IN_CLUSTER=true"
echo "  K8S_NAMESPACE=$NAMESPACE"
echo "  GKE_AUTOPILOT_ENABLED=true"
echo "  GPU_ENABLED=true"
echo "  GPU_TYPE=nvidia-l4"
echo "  GPU_COUNT=1"
echo ""
echo "For image streaming, push your terminal image to Artifact Registry:"
echo "  gcloud artifacts repositories create terminals --repository-format=docker --location=$REGION"
echo "  docker tag terminal-server:latest $REGION-docker.pkg.dev/$PROJECT_ID/terminals/terminal-server:latest"
echo "  docker push $REGION-docker.pkg.dev/$PROJECT_ID/terminals/terminal-server:latest"
echo ""
echo "Then set:"
echo "  TERMINAL_IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/terminals/terminal-server:latest"
echo ""
echo "=== GPU Quota ==="
echo ""
echo "Ensure you have GPU quota in $REGION. Check at:"
echo "  https://console.cloud.google.com/iam-admin/quotas?project=$PROJECT_ID"
echo ""
echo "Request quota for:"
echo "  - NVIDIA L4 GPUs (recommended, cost-effective)"
echo "  - NVIDIA T4 GPUs (alternative)"
echo ""
