#!/bin/bash

source set_variables.sh

docker-compose -p $DOCKER_COMPOSE_PROJECT -f docker/dependencies.yml -f docker/dev.yml --profile dev up -d --no-recreate

sleep 10

docker logs $USER-airt-service-devel 2>&1 | grep token
