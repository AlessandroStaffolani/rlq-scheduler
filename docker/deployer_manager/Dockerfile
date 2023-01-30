FROM rlq/base

#ARG SERVER_USER=deployer_manager
#
#COPY docker/deployer_manager/create-linux-user.sh /opt/create-linux-user.sh
#RUN chmod +x /opt/create-linux-user.sh
#
#RUN /opt/create-linux-user.sh

# create worker pid and log folder
RUN mkdir -p /var/log/deployer_manager
# RUN chown -R $SERVER_USER:$SERVER_USER /var/log/deployer_manager

WORKDIR /opt/rlq/deployer_manager

COPY requirements/deployer_manager.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY docker/deployer_manager/run.sh ./
RUN chmod +x /opt/rlq/deployer_manager/run.sh

COPY config/global.yml ./config/global.yml
COPY config/deployer_manager.yml ./config/deployer_manager.yml
COPY rlq_scheduler/deployer_manager ./rlq_scheduler/deployer_manager
COPY rlq_scheduler/common ./rlq_scheduler/common
RUN touch ./rlq_scheduler/__init__.py

#RUN chown -R $SERVER_USER:$SERVER_USER ./
#
#USER $SERVER_USER

EXPOSE 9093

ENV DM_SERVER_MODULE=rlq_scheduler.deployer_manager.server
ENV DM_SERVER_CONFIG_FILENAME=/opt/rlq/deployer_manager/config/deployer_manager.yml
ENV GLOBAL_CONFIG_FILENAME=/opt/rlq/deployer_manager/config/global.yml
# ENV SERVER_USER=$SERVER_USER

# running agent server
CMD ["/bin/bash", "run.sh"]