#!/usr/bin/bash

if test -n "$RUN_NGINX"
    ./make_nginx_conf.sh
    cat /etc/nginx/conf.d/default.conf

    service nginx start
    service nginx status

    export SSL_CERT="/letsencrypt/live/$DOMAIN/fullchain.pem"
    export SSL_KEY="/letsencrypt/live/$DOMAIN/privkey.pem"
end

# echo $DB_USERNAME $DB_PASSWORD $DB_HOST $DB_PORT $DB_DATABASE $DB_DATABASE_SERVER

check_db_is_up
alembic upgrade head
create_initial_users

make start_airflow

# set WORKERS (math 1'*'(getconf _NPROCESSORS_ONLN))
# ToDo: Use the following line once the topic processing loop commands are added
# uvicorn webservice:app --port 6006 --host 0.0.0.0 --workers=3 --proxy-headers &
uvicorn webservice:app --port 6006 --host 0.0.0.0 --workers=3 --proxy-headers
