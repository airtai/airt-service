#!/bin/bash


if test -z "$CI_REGISTRY_IMAGE"
then
	echo "INFO: CI_REGISTRY_IMAGE variable not set, setting it to 'ghcr.io/airtai/airt-service'"
	export CI_REGISTRY_IMAGE="ghcr.io/airtai/airt-service"
fi

if test -z "$TAG"
then
	echo "ERROR: TAG variable must be defined, exiting"
	exit -1
fi

if test -z "$CI_REGISTRY"
then
	echo "INFO: CI_REGISTRY variable not set, setting it to 'ghcr.io'"
	export CI_REGISTRY="ghcr.io"
fi

if test -z "$CI_REGISTRY_USER"
then
	echo "ERROR: CI_REGISTRY_USER variable must be defined, exiting"
	exit -1
fi

if test -z "$CI_REGISTRY_PASSWORD"
then
	echo "ERROR: CI_REGISTRY_PASSWORD variable must be defined, exiting"
	exit -1
fi


if [ ! -f key.pem ]; then
    echo "ERROR: key.pem file not found"
    exit -1
fi


if test -z "$DOMAIN"
then
	echo "ERROR: DOMAIN variable must be defined, exiting"
	exit -1
fi

if test -z "$INFOBIP_DOMAIN"
then
	echo "ERROR: INFOBIP_DOMAIN variable must be defined, exiting"
	exit -1
fi

if test -z "$AIRT_SERVICE_SUPER_USER_PASSWORD"
then
	echo "ERROR: AIRT_SERVICE_SUPER_USER_PASSWORD variable must be defined, exiting"
	exit -1
fi

if test -z "$DB_USERNAME"
then
	echo "ERROR: DB_USERNAME variable must be defined, exiting"
	exit -1
fi

if test -z "$DB_PASSWORD"
then
	echo "ERROR: DB_PASSWORD variable must be defined, exiting"
	exit -1
fi

if test -z "$DB_HOST"
then
	echo "ERROR: DB_HOST variable must be defined, exiting"
	exit -1
fi

if test -z "$DB_PORT"
then
	echo "ERROR: DB_PORT variable must be defined, exiting"
	exit -1
fi

if test -z "$DB_DATABASE"
then
	echo "ERROR: DB_DATABASE variable must be defined, exiting"
	exit -1
fi

if test -z "$DB_DATABASE_SERVER"
then
	echo "ERROR: DB_DATABASE_SERVER variable must be defined, exiting"
	exit -1
fi

if test -z "$AIRT_TOKEN_SECRET_KEY"
then
	echo "ERROR: AIRT_TOKEN_SECRET_KEY variable must be defined, exiting"
	exit -1
fi

if test -z "$STORAGE_BUCKET_PREFIX"
then
	echo "ERROR: STORAGE_BUCKET_PREFIX variable must be defined, exiting"
	exit -1
fi

if test -z "$AWS_ACCESS_KEY_ID"
then
	echo "ERROR: AWS_ACCESS_KEY_ID variable must be defined, exiting"
	exit -1
fi

if test -z "$AWS_SECRET_ACCESS_KEY"
then
	echo "ERROR: AWS_SECRET_ACCESS_KEY variable must be defined, exiting"
	exit -1
fi

if test -z "$AWS_DEFAULT_REGION"
then
	echo "ERROR: AWS_DEFAULT_REGION variable must be defined, exiting"
	exit -1
fi

echo "INFO: stopping already running docker container"
ssh -i key.pem ubuntu@"$DOMAIN" "set -a && source .env && set +a && docker-compose -p airt-service -f docker/dependencies.yml -f docker/base-server.yml -f docker/server.yml down || echo 'No containers available to stop'"
ssh -i key.pem ubuntu@"$DOMAIN" "docker container prune -f || echo 'No stopped containers to delete'"

echo "INFO: copying docker compose files to server"
ssh -i key.pem ubuntu@"$DOMAIN" "rm -rf /home/ubuntu/docker"
scp -i key.pem -r ./docker ubuntu@"$DOMAIN":/home/ubuntu/docker

echo "INFO: copying .env file to server"
ssh -i key.pem ubuntu@"$DOMAIN" "rm -rf /home/ubuntu/.env"
scp -i key.pem .env ubuntu@"$DOMAIN":/home/ubuntu/.env

echo "INFO: Creating storage directory if it doesn't exists"
ssh -i key.pem ubuntu@"$DOMAIN" "mkdir -p /home/ubuntu/storage"

echo "INFO: pulling docker images"
ssh -i key.pem ubuntu@"$DOMAIN" "echo $CI_REGISTRY_PASSWORD | docker login -u '$CI_REGISTRY_USER' --password-stdin '$CI_REGISTRY'"
ssh -i key.pem ubuntu@"$DOMAIN" "docker pull '$CI_REGISTRY_IMAGE':'$TAG'"
sleep 10

echo "INFO: starting docker containers using compose files"
ssh -i key.pem ubuntu@"$DOMAIN" "set -a && source .env && set +a && docker-compose -p airt-service -f docker/dependencies.yml -f docker/base-server.yml -f docker/server.yml up -d --no-recreate"
ssh -i key.pem ubuntu@"$DOMAIN" "docker system prune -f || echo 'No images to delete'"
