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


export TEST_USERNAME=$(python3 -c "import random, string; print(''.join(random.choice(string.ascii_lowercase) for _ in range(10)))")
export TEST_PASSWORD=$(python3 -c "import random, string; print(''.join(random.choice(string.ascii_lowercase) for _ in range(10)))")

echo Created username is $TEST_USERNAME

curl -X 'POST' \
    "${WEBSITE}/user/" \
    -H 'accept: application/json' \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H 'Content-Type: application/json' \
    -d "{
    \"username\": \"${TEST_USERNAME}\",
    \"first_name\": \"${TEST_USERNAME}\",
    \"last_name\": \"${TEST_USERNAME}\",
    \"email\": \"${TEST_USERNAME}@example.com\",
    \"subscription_type\": \"small\",
    \"super_user\": false,
    \"password\": \"${TEST_PASSWORD}\"
}" > /dev/null


export AIRT_SERVICE_TOKEN=$(curl -X 'POST'  ${WEBSITE}/token \
    -H 'accept: application/json' \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "username=${TEST_USERNAME}" --data-urlencode "password=${TEST_PASSWORD}" | \
    python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
