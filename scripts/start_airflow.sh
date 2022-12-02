#!/bin/bash

AIRFLOW_VENV="${HOME}/airflow_venv"
if [ ! -f "${AIRFLOW_VENV}/bin/airflow" ]; then
    echo "airflow not found"
    exit -1
fi

if pgrep -x "airflow" > /dev/null
then
    echo "airflow running already"
else
    source "${AIRFLOW_VENV}/bin/activate"

    if ! command -v mysql &> /dev/null
    then
        sudo apt update
        sudo apt install -y mysql-client
    fi

    mysql --user="${DB_USERNAME}" --password="${DB_PASSWORD}" --host="${DB_HOST}" --port="${DB_PORT}" --execute="CREATE DATABASE IF NOT EXISTS airflow CHARACTER SET utf8 COLLATE utf8_unicode_ci; CREATE USER IF NOT EXISTS 'airflow' IDENTIFIED BY 'airflow'; GRANT ALL PRIVILEGES ON airflow.* TO 'airflow';"
    airflow db init
    airflow users  create --role Admin --username admin --email info@airt.ai --firstname admin --lastname admin --password "${AIRFLOW_PASSWORD}"
    airflow connections add custom_azure_batch_default --conn-type azure_batch --conn-login testbatchnortheurope --conn-password ${SHARED_KEY_CREDENTIALS} --conn-extra '{"extra__azure_batch__account_url": "https://testbatchnortheurope.northeurope.batch.azure.com"}'

    airflow kerberos -D
    airflow scheduler -D
    airflow webserver -D
    deactivate

    echo "airflow started successfully"
fi
