#!/bin/sh
# quickly add hosts to a redirector
# usage: sh add_hosts.sh a.myhost.org b.myhost.org c.myhost.org

set -e

REDIRECTOR_URL=${REDIRECTOR_URL:-"http://127.0.0.1:9001"}

for host in $@; do
  curl -X POST -d "{\"host\": \"$host\"}" $REDIRECTOR_URL/hosts
done