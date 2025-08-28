#!/bin/bash
# Script to update the 'latest' tag to point to a specific version
# This fixes the deployment issue where latest wasn't pointing to 1.4.1

set -e

VERSION="${1:-1.4.1-beta}"
REGISTRY="ghcr.io"
IMAGE="cirisai/ciris-agent"

echo "🔄 Updating 'latest' tag to point to version: $VERSION"
echo "Registry: $REGISTRY"
echo "Image: $IMAGE"
echo ""

# Pull the specific version
echo "📥 Pulling $REGISTRY/$IMAGE:$VERSION..."
docker pull "$REGISTRY/$IMAGE:$VERSION"

# Tag it as latest
echo "🏷️  Tagging as latest..."
docker tag "$REGISTRY/$IMAGE:$VERSION" "$REGISTRY/$IMAGE:latest"

# Push the latest tag
echo "📤 Pushing latest tag..."
docker push "$REGISTRY/$IMAGE:latest"

echo ""
echo "✅ Successfully updated 'latest' tag to point to $VERSION"
echo ""
echo "To verify:"
echo "  docker pull $REGISTRY/$IMAGE:latest"
echo "  docker inspect $REGISTRY/$IMAGE:latest | grep -A 2 'RepoDigests'"
