#!/bin/bash

while read line; do export $line; done < .env

echo "Pushing into $DOCKER_REGISTRY_URL using username $DOCKER_REGISTRY_USERNAME"

cd ..
docker build --network=host -t service-broker/"$1" -f docker/"$1"/Dockerfile .
docker login --username="$DOCKER_REGISTRY_USERNAME" --password="$DOCKER_REGISTRY_PASSWORD" "$DOCKER_REGISTRY_URL"
docker tag service-broker/"$1" "$DOCKER_REGISTRY_URL"/"$IMAGE_PREFIX""$1"
docker push "$DOCKER_REGISTRY_URL"/"$IMAGE_PREFIX""$1"