FROM rlq/base

#ARG SERVER_USER=task_generator
#
#COPY docker/task_generator/create-linux-user.sh /opt/create-linux-user.sh
#RUN chmod +x /opt/create-linux-user.sh
#
#RUN /opt/create-linux-user.sh

# create worker pid and log folder
RUN mkdir -p /var/log/task_generator
# RUN chown -R $SERVER_USER:$SERVER_USER /var/log/task_generator

WORKDIR /opt/rlq/task_generator

COPY requirements/task_generator.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY docker/task_generator/run.sh ./
RUN chmod +x /opt/rlq/task_generator/run.sh

COPY data/google-traces ./data/google-traces
COPY config/global.yml ./config/global.yml
COPY config/task_generator.yml ./config/task_generator.yml
COPY rlq_scheduler/task_generator ./rlq_scheduler/task_generator
COPY rlq_scheduler/common ./rlq_scheduler/common
COPY rlq_scheduler/__init__.py ./rlq_scheduler/__init__.py
COPY rlq_scheduler/celery_app.py ./rlq_scheduler/celery_app.py
COPY rlq_scheduler/tasks ./rlq_scheduler/tasks

# RUN chown -R $SERVER_USER:$SERVER_USER ./

# USER $SERVER_USER

EXPOSE 9093

ENV TASK_GENERATOR_SERVER_MODULE=rlq_scheduler.task_generator.server
ENV TASK_GENERATOR_SERVER_CONFIG_FILENAME=/opt/rlq/task_generator/config/task_generator.yml
ENV GLOBAL_CONFIG_FILENAME=/opt/rlq/task_generator/config/global.yml
# ENV SERVER_USER=$SERVER_USER

# running agent server
CMD ["/bin/bash", "run.sh"]