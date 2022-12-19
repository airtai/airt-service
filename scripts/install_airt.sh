#!/bin/bash

if [ -n "${ACCESS_REP_TOKEN}" ] ; then
    FORMAT="oauth2:${ACCESS_REP_TOKEN}"
elif [ -n "${CI_JOB_TOKEN}" ] ; then
    FORMAT="gitlab-ci-token:${CI_JOB_TOKEN}"
else
    echo ERROR: Neither ACCESS_REP_TOKEN nor CI_JOB_TOKEN defined, exiting && exit -1
fi

REPO="https://${FORMAT}@gitlab.com/airt.ai/airt.git"


# To get current branch in git
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" == "HEAD" ]; then
    echo "Running in GitLab CI"
    if [[ -n ${CI_COMMIT_TAG} ]]; then
        echo "Running Tag build"
        BRANCH="main"
    else
        echo "Running normal build"
        BRANCH=$(git branch --remote --verbose --no-abbrev --contains | sed -rne 's/^[^\/]*\/([^\ ]+).*$/\1/p' | tail -1)
    fi
fi

echo "AIRT-SERVICE BRANCH=${BRANCH}"

# Check branch available in remote airt
git ls-remote --heads ${REPO} ${BRANCH} | grep ${BRANCH} >/dev/null
if [ "$?" == "1" ]; then
    echo "BRANCH ${BRANCH} not found in airt; Using dev instead"
    BRANCH=dev
fi

if test -z "$BRANCH"
then
      BRANCH=dev
fi

echo "REPO=${REPO}"
echo "AIRT BRANCH=${BRANCH}"
pip install git+${REPO}@${BRANCH}
