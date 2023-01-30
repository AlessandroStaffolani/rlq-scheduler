#!/bin/bash

echo "Starting Task Broker script"

celery -A "$CELERY_APP" worker --concurrency=1 -E -l INFO -n "$WORKER_NAME@%h" -Q "$WORKER_QUEUES" --pidfile=/var/run/celery/%n.pid --logfile=/var/log/celery/"$WORKER_NAME".log

# celery multi start worker -A "$CELERY_APP" --concurrency=1 -E -l info --pidfile=/var/run/celery/%n.pid --logfile=/var/log/celery/%p.log -n "$WORKER_NAME@%h" -Q "$WORKER_QUEUES"

# tail -f /dev/null
