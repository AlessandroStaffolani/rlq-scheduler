#!/bin/sh

addgroup --gid 1000 "$SERVER_USER"
adduser --system --disabled-password --uid 1000 --gid 1000 "$SERVER_USER"
