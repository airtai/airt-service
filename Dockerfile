ARG TAG

ARG BASE_IMAGE=ubuntu:22.04

FROM $BASE_IMAGE

ARG AIRT_LIB_BRANCH
# Token to authenticate for airtlib
ARG CI_JOB_TOKEN
ARG ACCESS_REP_TOKEN

SHELL ["/bin/bash", "-c"]

COPY assets ./assets
COPY migrations ./migrations
COPY scripts ./scripts

# needed to suppress tons of debconf messages
ENV DEBIAN_FRONTEND noninteractive

RUN apt update --fix-missing && apt upgrade --yes \
    && apt install -y software-properties-common apt-utils build-essential \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt update \
    && apt install -y --no-install-recommends nginx mysql-client python3.9-dev python3.9-distutils python3-pip python3-apt \
    gettext-base default-libmysqlclient-dev virtualenv unattended-upgrades git wget curl \
    && apt purge --auto-remove \
    && apt clean \
    && rm -rf /var/lib/apt/lists/*

# Install node and npm
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && apt-get install -y nodejs \
    && apt purge --auto-remove && apt clean && rm -rf /var/lib/apt/lists/*

# Install confluent CLI
RUN curl -sL --http1.1 https://cnfl.io/cli | sh -s -- -b /usr/local/bin v2.37.0

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.9 1
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 2
RUN update-alternatives --set python3 /usr/bin/python3.9
RUN python3 -m pip install --upgrade pip

# Install airt-lib
RUN if [ -n "$ACCESS_REP_TOKEN" ] ; \
    then pip3 install git+https://oauth2:${ACCESS_REP_TOKEN}@gitlab.com/airt.ai/airt.git@${AIRT_LIB_BRANCH} ; \
    else pip3 install git+https://gitlab-ci-token:${CI_JOB_TOKEN}@gitlab.com/airt.ai/airt.git@${AIRT_LIB_BRANCH} ; \
    fi

COPY webservice.py dist/airt_service-*-py3-none-any.whl ws/* settings.ini alembic.ini errors.yml batch_environment.yml azure_batch_environment.yml Makefile \
    airflow.cfg setup.py README.md ./
RUN pip install -e '.[dev]'
RUN pip install airt_service-*-py3-none-any.whl

RUN fastkafka docs install_deps
RUN fastkafka docs generate webservice:fast_kafka_api_app

# RUN groupadd -r airt
# RUN useradd -r -g airt airt
RUN touch /var/run/nginx.pid && \
  mkdir -p /var/cache/nginx /var/log/nginx /etc/nginx/conf.d /var/lib/nginx/ && \
  chown -R 755 /var/run/nginx.pid && \
  chown -R 755 /var/cache/nginx && \
  chown -R 755 /var/log/nginx && \
  chown -R 755 /etc/nginx/conf.d && \
  chown -R 755 /var/lib/nginx/

ENV DOMAIN=""

EXPOSE 6006

# run container as non-root user
# RUN groupadd -r airt
# RUN useradd -r -g airt non-root
# USER airt

ENTRYPOINT []
CMD [ "/usr/bin/bash", "-c", "./start_webservice.sh" ]
