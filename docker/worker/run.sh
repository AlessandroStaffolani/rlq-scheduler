#!/bin/bash

echo "Starting $WORKER_NAME script"

celery -A "$CELERY_APP" worker --concurrency=1 -E -l INFO -n "$WORKER_NAME@%h" -Q "$WORKER_QUEUES" --pidfile=/var/run/celery/%n.pid --logfile=/var/log/celery/"$WORKER_NAME".log

#celery -A "$CELERY_APP" multi start worker --concurrency=1 -E -l INFO --pidfile=/var/run/celery/%n.pid --logfile=/var/log/celery/%p.log -n "$WORKER_NAME@%h" -Q "$WORKER_QUEUES"

#tail -f /dev/null
