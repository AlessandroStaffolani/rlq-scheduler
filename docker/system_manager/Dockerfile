FROM rlq/base

#ARG SERVER_USER=system_manager
#
#COPY docker/system_manager/create-linux-user.sh /opt/create-linux-user.sh
#RUN chmod +x /opt/create-linux-user.sh
#
#RUN /opt/create-linux-user.sh

# create worker pid and log folder
RUN mkdir -p /var/log/system_manager
# RUN chown -R $SERVER_USER:$SERVER_USER /var/log/system_manager

WORKDIR /opt/rlq/system_manager

COPY requirements/system_manager.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY docker/system_manager/run.sh ./
RUN chmod +x /opt/rlq/system_manager/run.sh

COPY data/google-traces ./data/google-traces
COPY config/global.yml ./config/global.yml
COPY config/system_manager.yml ./config/system_manager.yml
COPY config/multi_run_config.yml ./config/multi_run_config.yml
COPY rlq_scheduler/system_manager ./rlq_scheduler/system_manager
COPY rlq_scheduler/common ./rlq_scheduler/common
COPY rlq_scheduler/__init__.py ./rlq_scheduler/__init__.py
COPY rlq_scheduler/celery_app.py ./rlq_scheduler/celery_app.py
COPY rlq_scheduler/tasks ./rlq_scheduler/tasks

# RUN chown -R $SERVER_USER:$SERVER_USER ./

# USER $SERVER_USER

EXPOSE 9092

ENV SYSTEM_MANAGER_SERVER_MODULE=rlq_scheduler.system_manager.server
ENV SYSTEM_MANAGER_SERVER_CONFIG_FILENAME=/opt/rlq/system_manager/config/system_manager.yml
ENV SYSTEM_MANAGER_MULTI_RUN_CONFIG_FILENAME=/opt/rlq/system_manager/config/multi_run_config.yml
ENV GLOBAL_CONFIG_FILENAME=/opt/rlq/system_manager/config/global.yml
# ENV SERVER_USER=$SERVER_USER

# running agent server
CMD ["/bin/bash", "run.sh"]