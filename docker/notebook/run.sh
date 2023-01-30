#!/bin/bash

if [[ -z "${ENTERPRISE_GATEWAY_HOST_IP}" ]]; then
  echo "Starting jupyter notebook in local mode"
  jupyter notebook --no-browser --ip=0.0.0.0 --notebook-dir=/jupyter --allow-root
else
  echo "Starting jupyter notebook in remote gateway mode"
  jupyter notebook --gateway-url=http://"$ENTERPRISE_GATEWAY_HOST_IP":"$ENTERPRISE_GATEWAY_PORT" --no-browser --ip=0.0.0.0 --notebook-dir=/jupyter --allow-root
fi