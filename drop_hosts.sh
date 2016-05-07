#!/bin/sh
# quickly drop hosts to a redirector
# usage: sh drop_hosts.sh a.myhost.org b.myhost.org c.myhost.org

set -e

REDIRECTOR_URL=${REDIRECTOR_URL:-"http://127.0.0.1:9001"}

for host in $@; do
  curl -X DELETE -d "{\"host\": \"$host\"}" $REDIRECTOR_URL/hosts
done
