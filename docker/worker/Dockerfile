FROM rlq/base

# create worker pid and log folder
RUN mkdir -p /var/run/celery
RUN mkdir -p /var/log/celery
# RUN chown -R $CELERY_USER:$CELERY_USER /var/run/celery
# RUN chown -R $CELERY_USER:$CELERY_USER /var/log/celery

WORKDIR /opt/rlq/worker

COPY requirements/worker.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY docker/worker/run.sh ./

COPY data/google-traces ./data/google-traces
COPY config/global.yml ./config/global.yml
COPY rlq_scheduler/__init__.py ./rlq_scheduler/__init__.py
COPY rlq_scheduler/celery_app.py ./rlq_scheduler/celery_app.py
COPY rlq_scheduler/tasks ./rlq_scheduler/tasks
COPY rlq_scheduler/common ./rlq_scheduler/common

ENV CELERY_APP=rlq_scheduler

# Running worker
CMD ["/bin/bash", "run.sh"]