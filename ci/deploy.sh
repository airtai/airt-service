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

if test -z "$GITHUB_USERNAME"
then
	echo "ERROR: GITHUB_USERNAME variable must be defined, exiting"
	exit -1
fi

if test -z "$GITHUB_PASSWORD"
then
	echo "ERROR: GITHUB_PASSWORD variable must be defined, exiting"
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
ssh -o StrictHostKeyChecking=no -i key.pem azureuser@"$DOMAIN" "set -a && source .env && set +a && docker-compose -p airt-service -f docker/dependencies.yml -f docker/base-server.yml -f docker/server.yml down || echo 'No containers available to stop'"
ssh -o StrictHostKeyChecking=no -i key.pem azureuser@"$DOMAIN" "docker container prune -f || echo 'No stopped containers to delete'"

echo "INFO: copying docker compose files to server"
ssh -o StrictHostKeyChecking=no -i key.pem azureuser@"$DOMAIN" "rm -rf /home/ubuntu/docker"
scp -o StrictHostKeyChecking=no -i key.pem -r ./docker azureuser@"$DOMAIN":/home/ubuntu/docker

echo "INFO: copying .env file to server"
ssh -o StrictHostKeyChecking=no -i key.pem azureuser@"$DOMAIN" "rm -rf /home/ubuntu/.env"
scp -o StrictHostKeyChecking=no -i key.pem .env azureuser@"$DOMAIN":/home/ubuntu/.env

echo "INFO: Creating storage directory if it doesn't exists"
ssh -o StrictHostKeyChecking=no -i key.pem azureuser@"$DOMAIN" "mkdir -p /home/ubuntu/storage"

echo "INFO: pulling docker images"
ssh -o StrictHostKeyChecking=no -i key.pem azureuser@"$DOMAIN" "echo $GITHUB_PASSWORD | docker login -u '$GITHUB_USERNAME' --password-stdin '$CI_REGISTRY'"
ssh -o StrictHostKeyChecking=no -i key.pem azureuser@"$DOMAIN" "docker pull '$CI_REGISTRY_IMAGE':'$TAG'"
sleep 10

echo "Deleting old images"
ssh -o StrictHostKeyChecking=no -i key.pem azureuser@"$DOMAIN" "docker system prune -f || echo 'No images to delete'"

echo "INFO: starting docker containers using compose files"
ssh -o StrictHostKeyChecking=no -i key.pem azureuser@"$DOMAIN" "set -a && source .env && set +a && docker-compose -p airt-service -f docker/dependencies.yml -f docker/base-server.yml -f docker/server.yml up -d --no-recreate"
