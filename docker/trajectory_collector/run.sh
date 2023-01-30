#!/bin/bash

# gunicorn -k gevent --worker-connections 500 -t 120 -b 0.0.0.0:9091 -u "$SERVER_USER" -g "$SERVER_USER" "$TC_SERVER_MODULE:create_server('$TC_SERVER_CONFIG_FILENAME', '$GLOBAL_CONFIG_FILENAME')"

gunicorn -t 600 -w 1 -b 0.0.0.0:9091 "$TC_SERVER_MODULE:create_server('$TC_SERVER_CONFIG_FILENAME', '$GLOBAL_CONFIG_FILENAME')"