#!/bin/bash

# gunicorn -k gevent --worker-connections 500 -t 120 -b 0.0.0.0:9093 -u "$SERVER_USER" -g "$SERVER_USER" "$DM_SERVER_MODULE:create_server('$DM_SERVER_CONFIG_FILENAME', '$GLOBAL_CONFIG_FILENAME')"

gunicorn -t 600 -w 1 -b 0.0.0.0:9093 "$DM_SERVER_MODULE:create_server('$DM_SERVER_CONFIG_FILENAME', '$GLOBAL_CONFIG_FILENAME')"