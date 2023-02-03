#!/bin/bash

# sh ./build-and-pull.sh deployer_manager
sh ./build-and-pull.sh base
sh ./build-and-pull.sh agent
sh ./build-and-pull.sh flower
sh ./build-and-pull.sh system_manager
sh ./build-and-pull.sh task_broker
sh ./build-and-pull.sh task_generator
sh ./build-and-pull.sh trajectory_collector
sh ./build-and-pull.sh worker

echo "All the images have been built and pushed on the registry"