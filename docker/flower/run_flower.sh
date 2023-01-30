#!/bin/bash

# flower --broker=amqp://guest@${BROKER_SERVICE_SERVICE_HOST:localhost}:5672//

flower --broker=redis://${BROKER_SERVICE_SERVICE_HOST:localhost}:6379/${CELERY_REDIS_DB}
