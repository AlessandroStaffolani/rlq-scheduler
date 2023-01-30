FROM python:3.8.2-slim-buster

RUN apt-get update && apt-get install -y gcc python3-dev

WORKDIR /opt/rlq/flower

RUN pip install --no-cache-dir -Iv flower redis celery==4.4.7

# Make sure we expose port 5555 so that we can connect to it
EXPOSE 5555

COPY docker/flower/run_flower.sh /usr/local/bin/run_flower.sh

# Running flower
CMD ["/bin/bash", "/usr/local/bin/run_flower.sh"]
