#!/bin/sh
# Container entrypoint for the china-abs toolbox image.
#
# cron does not hand its own environment to jobs, so snapshot the container
# environment (docker run --env-file / -e) into /etc/doctocloud.env and let the
# jobs in /etc/cron.d/doctocloud source it.  Then start the cron daemon and hand
# off to the command (default: sleep infinity).
set -eu

if [ ! -f /etc/doctocloud.env ]; then
    umask 077
    printenv | while IFS='=' read -r key value; do
        case "$key" in
            '' | *[!A-Za-z0-9_]* | [0-9]*) continue ;;
        esac
        escaped=$(printf '%s' "$value" | sed "s/'/'\\\\''/g")
        printf "export %s='%s'\n" "$key" "$escaped"
    done > /etc/doctocloud.env
fi

/usr/sbin/cron

exec "$@"
