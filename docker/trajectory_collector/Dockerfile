FROM rlq/base

#ARG SERVER_USER=trajectory_collector
#
#COPY docker/agent/create-linux-user.sh /opt/create-linux-user.sh
#RUN chmod +x /opt/create-linux-user.sh
#
#RUN /opt/create-linux-user.sh

# create worker pid and log folder
RUN mkdir -p /var/log/trajectory_collector
# RUN chown -R $SERVER_USER:$SERVER_USER /var/log/trajectory_collector

WORKDIR /opt/rlq/trajectory_collector

COPY requirements/trajectory_collector.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY docker/trajectory_collector/run.sh ./
RUN chmod +x /opt/rlq/trajectory_collector/run.sh

COPY config/global.yml ./config/global.yml
COPY config/trajectory_collector.yml ./config/trajectory_collector.yml
COPY data ./data
COPY rlq_scheduler/trajectory_collector ./rlq_scheduler/trajectory_collector
COPY rlq_scheduler/common ./rlq_scheduler/common
COPY rlq_scheduler/__init__.py ./rlq_scheduler/__init__.py
COPY rlq_scheduler/celery_app.py ./rlq_scheduler/celery_app.py
COPY rlq_scheduler/tasks ./rlq_scheduler/tasks

# RUN chown -R $SERVER_USER:$SERVER_USER ./

# USER $SERVER_USER

EXPOSE 9091

ENV TC_SERVER_MODULE=rlq_scheduler.trajectory_collector.server
ENV TC_SERVER_CONFIG_FILENAME=/opt/rlq/trajectory_collector/config/trajectory_collector.yml
ENV GLOBAL_CONFIG_FILENAME=/opt/rlq/trajectory_collector/config/global.yml
# ENV SERVER_USER=$SERVER_USER

# running agent server
CMD ["/bin/bash", "run.sh"]