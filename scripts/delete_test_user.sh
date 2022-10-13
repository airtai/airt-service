#!/bin/bash

set -a && source .env* && set +a
ADMIN_TOKEN=$(curl -X 'POST'  ${WEBSITE}/token \
    -H 'accept: application/json' \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "username=kumaran" --data-urlencode "password=${AIRT_SERVICE_SUPER_USER_PASSWORD}" | \
    python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

if test -z "$ADMIN_TOKEN"; then
	echo ERROR: Unable to get login token, please start webservice by running "make serve_webservice" command in docker terminal
	exit -1
fi


curl -X 'POST' \
    "${WEBSITE}/user/cleanup" \
    -H 'accept: application/json' \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "{
    \"username\": \"${TEST_USERNAME}\"
}" > /dev/null

echo Deleted username $TEST_USERNAME
