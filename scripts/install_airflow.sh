#!/bin/bash

if ! command -v virtualenv &> /dev/null
then
    pip install virtualenv
fi

AIRFLOW_VENV="${HOME}/airflow_venv"
if [ ! -d "$AIRFLOW_VENV" ]; then
    # echo "${AIRFLOW_VENV}"
    virtualenv "${AIRFLOW_VENV}" -p python3
fi

if [ ! -f "${AIRFLOW_VENV}/bin/airflow" ]; then
    source "${AIRFLOW_VENV}/bin/activate"
    pip install mysqlclient==2.1.1
    pip install "apache-airflow==2.5.1" --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.5.1/constraints-3.9.txt"
    pip install apache-airflow-providers-amazon==7.2.1
    pip install apache-airflow-providers-microsoft-azure==5.2.1
    deactivate
    mkdir -p $HOME/airflow
    mkdir -p $HOME/airflow/dags
    envsubst '${HOME},${SSL_CERT},${SSL_KEY}' < airflow.cfg >$HOME/airflow/airflow.cfg
fi
