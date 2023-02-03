#!/bin/bash

while read line; do export $line; done < .env

echo "Pulling from $DOCKER_REGISTRY_URL using username $DOCKER_REGISTRY_USERNAME"

docker login --username="$DOCKER_REGISTRY_USERNAME" --password="$DOCKER_REGISTRY_PASSWORD" "$DOCKER_REGISTRY_URL"

docker pull cloud.canister.io:5000/"$IMAGE_PREFIX"base
docker pull cloud.canister.io:5000/"$IMAGE_PREFIX"agent
docker pull cloud.canister.io:5000/"$IMAGE_PREFIX"task_broker
docker pull cloud.canister.io:5000/"$IMAGE_PREFIX"task_generator
docker pull cloud.canister.io:5000/"$IMAGE_PREFIX"trajectory_collector
docker pull cloud.canister.io:5000/"$IMAGE_PREFIX"system_manager
docker pull cloud.canister.io:5000/"$IMAGE_PREFIX"worker
docker pull cloud.canister.io:5000/"$IMAGE_PREFIX"flower
docker pull cloud.canister.io:5000/"$IMAGE_PREFIX"redis
