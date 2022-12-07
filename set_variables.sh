#!/bin/bash

export AIRT_SERVER_DOCKER=ghcr.io/airtai/nbdev-mkdocs:latest

echo PORT_PREFIX variable set to $PORT_PREFIX

export AIRT_JUPYTER_PORT="${PORT_PREFIX}8888"
echo AIRT_JUPYTER_PORT variable set to $AIRT_JUPYTER_PORT

export AIRT_TB_PORT="${PORT_PREFIX}6006"
echo AIRT_TB_PORT variable set to $AIRT_TB_PORT

export AIRT_DASK_PORT="${PORT_PREFIX}8787"
echo AIRT_DASK_PORT variable set to $AIRT_DASK_PORT

export AIRT_DOCS_PORT="${PORT_PREFIX}4000"
echo AIRT_DOCS_PORT variable set to $AIRT_DOCS_PORT

export AIRFLOW_PORT="${PORT_PREFIX}8080"
echo AIRFLOW_PORT variable set to $AIRFLOW_PORT


if test -z "$AIRT_PROJECT"
then
      echo 'AIRT_PROJECT variable not set, setting to current directory'
      export AIRT_PROJECT=`pwd`
fi
echo AIRT_PROJECT variable set to $AIRT_PROJECT

# Check .env.dev.* file exists and copy from template if it does not exists
if [ ! -f .env.dev.config ]; then
      cp .env.template.config .env.dev.config
fi

if [ ! -f .env.dev.secrets ]; then
      cp .env.template.secrets .env.dev.secrets
      echo 'Please update the environment variable values in file .env.dev.config, .env.dev.secrets and rerun the script'
      exit -1
fi

# Run envsubst for .env.dev.* files
cp .env.dev.config /tmp/airt-service.env.dev.config && envsubst < /tmp/airt-service.env.dev.config > .env.dev.config && rm /tmp/airt-service.env.dev.config
cp .env.dev.secrets /tmp/airt-service.env.dev.secrets && envsubst < /tmp/airt-service.env.dev.secrets > .env.dev.secrets && rm /tmp/airt-service.env.dev.secrets
# Export values in .env.dev.* files as environment variables for validation
set -a && source .env.dev.config && source .env.dev.secrets && set +a

if test -z "$ACCESS_REP_TOKEN"; then
	echo ERROR: ACCESS_REP_TOKEN must be defined in .env.dev.secrets file, exiting
	exit -1
fi

if test -z "$AIRT_SERVICE_SUPER_USER_PASSWORD"
then
      echo 'AIRT_SERVICE_SUPER_USER_PASSWORD variable not set in .env.dev.secrets file, exiting'
      exit -1
fi

if test -z "$AIRT_TOKEN_SECRET_KEY"
then
      echo 'AIRT_TOKEN_SECRET_KEY variable not set in .env.dev.secrets file, exiting'
      exit -1
fi

if test -z "$AWS_ACCESS_KEY_ID"
then
      echo 'AWS_ACCESS_KEY_ID variable not set in .env.dev.secrets file, exiting'
      exit -1
fi

if test -z "$AWS_SECRET_ACCESS_KEY"
then
      echo 'AWS_SECRET_ACCESS_KEY variable not set in .env.dev.secrets file, exiting'
      exit -1
fi

if test -z "$STORAGE_BUCKET_PREFIX"
then
      echo 'STORAGE_BUCKET_PREFIX variable not set in .env.dev.secrets file, exiting'
      exit -1
fi

if test -z "$CLICKHOUSE_HOST"
then
      echo 'Clickhouse variables not set in .env.dev.secrets file, exiting'
      exit -1
fi

export DOCKER_COMPOSE_PROJECT="${USER}-airt-service"
echo DOCKER_COMPOSE_PROJECT variable set to $DOCKER_COMPOSE_PROJECT

echo Using $AIRT_SERVER_DOCKER
docker image ls $AIRT_SERVER_DOCKER

