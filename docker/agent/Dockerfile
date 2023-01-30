FROM rlq/base

#ARG SERVER_USER=agent
#
#COPY docker/agent/create-linux-user.sh /opt/create-linux-user.sh
#RUN chmod +x /opt/create-linux-user.sh
#
#RUN /opt/create-linux-user.sh

# create worker pid and log folder
RUN mkdir -p /var/log/agent
# RUN chown -R $SERVER_USER:$SERVER_USER /var/log/agent

WORKDIR /opt/rlq/agent

COPY requirements/agent.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY docker/agent/run.sh ./
RUN chmod +x /opt/rlq/agent/run.sh

COPY data/google-traces ./data/google-traces
COPY config/global.yml ./config/global.yml
COPY config/agent.yml ./config/agent.yml
COPY rlq_scheduler/agent ./rlq_scheduler/agent
COPY rlq_scheduler/common ./rlq_scheduler/common
RUN touch ./rlq_scheduler/__init__.py

# RUN chown -R $SERVER_USER:$SERVER_USER ./

# USER $SERVER_USER

EXPOSE 9090

ENV AGENT_SERVER_MODULE=rlq_scheduler.agent.server
ENV AGENT_SERVER_CONFIG_FILENAME=/opt/rlq/agent/config/agent.yml
ENV GLOBAL_CONFIG_FILENAME=/opt/rlq/agent/config/global.yml
# ENV SERVER_USER=$SERVER_USER

# running agent server
CMD ["/bin/bash", "run.sh"]