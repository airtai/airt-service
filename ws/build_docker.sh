#!/bin/bash


if test -z "$CI_REGISTRY_IMAGE"
then
	export CI_REGISTRY_IMAGE=ghcr.io/airtai/airt-service
fi

if test -z "$CI_COMMIT_REF_NAME"
then
	export CI_COMMIT_REF_NAME=$(git branch --show-current)
fi

if [ "$CI_COMMIT_REF_NAME" == "main" ]
then
    export TAG=latest
	export CACHE_FROM="latest"
	export AIRT_LIB_BRANCH="main"
else
    export TAG=$CI_COMMIT_REF_NAME
	export CACHE_FROM="dev"
	export AIRT_LIB_BRANCH="dev"
fi

echo Building $CI_REGISTRY_IMAGE

if test -z "$ACCESS_REP_TOKEN"; then
	if test -z "$CI_JOB_TOKEN"; then
		echo ERROR: ACCESS_REP_TOKEN must be defined, exiting
		exit -1
	else
		docker build --build-arg CI_JOB_TOKEN --build-arg AIRT_LIB_BRANCH=$AIRT_LIB_BRANCH --build-arg TAG=$CACHE_FROM --cache-from $CI_REGISTRY_IMAGE:$CACHE_FROM -t $CI_REGISTRY_IMAGE:$TAG .
	fi
else
	docker build --build-arg ACCESS_REP_TOKEN --build-arg AIRT_LIB_BRANCH=$AIRT_LIB_BRANCH --build-arg TAG=$CACHE_FROM --cache-from $CI_REGISTRY_IMAGE:$CACHE_FROM -t $CI_REGISTRY_IMAGE:$TAG .
fi

if [ "$CI_COMMIT_REF_NAME" == "main" ]
then
	docker tag $CI_REGISTRY_IMAGE:$TAG $CI_REGISTRY_IMAGE:$CI_COMMIT_REF_NAME
fi

# Initiate trivy
sh ./ws/check_docker.sh
