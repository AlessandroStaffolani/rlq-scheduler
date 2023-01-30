#!/bin/bash

# sh ./build.sh deployer_manager
sh ./build.sh base
sh ./build.sh agent
sh ./build.sh flower
sh ./build.sh system_manager
sh ./build.sh task_broker
sh ./build.sh task_generator
sh ./build.sh trajectory_collector
sh ./build.sh worker
sh ./build.sh offline_trainer

echo "All the images have been built and pushed on the registry"