#!/bin/bash

set -a && source .env.dev.secrets && set +a
export WEBSITE="http://0.0.0.0:${PORT_PREFIX}6006"


source scripts/create_test_user.sh


echo "Running DAST script"
docker run --rm -v $(pwd):/zap/wrk/:rw \
--network="host" \
-t owasp/zap2docker-stable:latest \
zap-api-scan.py -d \
-t http://0.0.0.0:${PORT_PREFIX}6006/openapi.json \
-f openapi \
-r dast-api-scan-report.html \
-z "-config replacer.full_list\\(0\\).description=auth1 \
-config replacer.full_list\\(0\\).enabled=true \
-config replacer.full_list\\(0\\).matchtype=REQ_HEADER \
-config replacer.full_list\\(0\\).matchstr=Authorization \
-config replacer.full_list\\(0\\).regex=false \
-config replacer.full_list\\(0\\).replacement=\"Bearer ${AIRT_SERVICE_TOKEN}\""


source scripts/delete_test_user.sh
