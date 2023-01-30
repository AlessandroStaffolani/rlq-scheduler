#!/bin/bash

echo "Starting docker build for $1"

cd ..
docker build --network=host -t service-broker/"$1" -f docker/"$1"/Dockerfile .

echo "Docker build for $1 completed"