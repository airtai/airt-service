#!/bin/bash

envsubst '${DOMAIN},${INFOBIP_DOMAIN}' < nginx.conf.template >/etc/nginx/conf.d/default.conf
