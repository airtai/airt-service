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

RUN add-apt-repository ppa:deadsnakes/ppa && apt update --fix-missing \
    && apt install -y --no-install-recommends nginx mysql-client python3.9-dev python3.9-distutils python3-pip \
    gettext-base default-libmysqlclient-dev virtualenv unattended-upgrades \
    && apt purge --auto-remove \
    && apt clean \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --set python3 /usr/bin/python3.9
RUN python3 -m pip install --upgrade pip

# Install airt-lib
RUN if [ -n "$ACCESS_REP_TOKEN" ] ; \
    then pip3 install git+https://oauth2:${ACCESS_REP_TOKEN}@gitlab.com/airt.ai/airt.git@${AIRT_LIB_BRANCH} ; \
    else pip3 install git+https://gitlab-ci-token:${CI_JOB_TOKEN}@gitlab.com/airt.ai/airt.git@${AIRT_LIB_BRANCH} ; \
    fi

# Enable unattended-upgrades and print the configuration.
# If the configuration output is "1" then the unattended upgrade will run every 1 day. If the number is "0" then unattended upgrades are disabled.
RUN dpkg-reconfigure --priority=low unattended-upgrades && apt-config dump APT::Periodic::Unattended-Upgrade
# The below command will check and run upgrade only once while building
RUN unattended-upgrade -d

COPY webservice.py dist/airt_service-*-py3-none-any.whl ws/* settings.ini alembic.ini errors.yml batch_environment.yml azure_batch_environment.yml Makefile airflow.cfg ./
RUN pip install -e '.[dev]'

RUN groupadd -r airt
RUN useradd -r -g airt airt
RUN touch /var/run/nginx.pid && \
  mkdir -p /var/cache/nginx /var/log/nginx /etc/nginx/conf.d /var/lib/nginx/ && \
  chown -R airt:airt /var/run/nginx.pid && \
  chown -R airt:airt /var/cache/nginx && \
  chown -R airt:airt /var/log/nginx && \
  chown -R airt:airt /etc/nginx/conf.d && \
  chown -R airt:airt /var/lib/nginx/

ENV DOMAIN=""

EXPOSE 6006

# run container as non-root user
# RUN groupadd -r airt
# RUN useradd -r -g airt non-root
USER airt

ENTRYPOINT []
CMD [ "/usr/bin/fish", "-c", "./start_webservice.sh" ]
