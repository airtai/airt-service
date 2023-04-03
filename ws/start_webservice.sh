#!/usr/bin/bash

if test -n "$RUN_NGINX";
then
    ./make_nginx_conf.sh
    cat /etc/nginx/conf.d/default.conf

    service nginx start
    service nginx status

    export SSL_CERT="/letsencrypt/live/$DOMAIN/fullchain.pem"
    export SSL_KEY="/letsencrypt/live/$DOMAIN/privkey.pem"
fi

# echo $DB_USERNAME $DB_PASSWORD $DB_HOST $DB_PORT $DB_DATABASE $DB_DATABASE_SERVER

check_db_is_up
alembic upgrade head
create_initial_users

make start_airflow

if [[ -z "${NUM_WORKERS}" ]]; then
  NUM_WORKERS=3
fi

echo NUM_WORKERS set to $NUM_WORKERS

fastkafka docs install_deps
fastkafka docs generate webservice:fast_kafka_api_app

if [[ $DOMAIN == "api.airt.ai" ]]; then
    KAFKA_BROKER="production"
elif [[ $DOMAIN == "api.staging.airt.ai" ]]; then
    KAFKA_BROKER="staging"
else
    KAFKA_BROKER="dev"
fi
echo KAFKA_BROKER value set to $KAFKA_BROKER

fastkafka run --num-workers $NUM_WORKERS --kafka-broker $KAFKA_BROKER webservice:fast_kafka_api_app > ./fastkafka.log & 

uvicorn webservice:app --port 6006 --host 0.0.0.0 --workers=$NUM_WORKERS --proxy-headers
