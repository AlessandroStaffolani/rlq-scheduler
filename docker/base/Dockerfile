FROM python:3.8-slim-buster

RUN apt-get update && apt-get install -y gcc python3-dev curl

COPY requirements/base.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt