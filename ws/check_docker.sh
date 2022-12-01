#!/bin/bash


if test -z "$CI_REGISTRY_IMAGE"
then
	export CI_REGISTRY_IMAGE=ghcr.io/airtai/airt-service
fi

if test -z "$CI_COMMIT_REF_NAME"
then
	export CI_COMMIT_REF_NAME=$(git branch --show-current)
fi


if [[ $CI_COMMIT_REF_NAME == "main" ]]; then TAG=latest ; else TAG=$CI_COMMIT_REF_NAME ; fi;

# this one is for the full report
# --timeout is increased to 10m because scanning images consistently results in timeout failure
# Please refer to: https://github.com/aquasecurity/trivy/issues/802
trivy image --timeout 10m -s CRITICAL,HIGH $CI_REGISTRY_IMAGE:$TAG
# this one will fail if needed
trivy image --timeout 10m --exit-code 1 --ignore-unfixed $CI_REGISTRY_IMAGE:$TAG
