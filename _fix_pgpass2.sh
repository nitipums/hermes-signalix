#!/usr/bin/env bash
set -e
cd /root/signalix
# The postgres container actually accepts 'signalix_pass' (verified from inside
# the backend network). Align .env to the REAL working password.
sed -i 's/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=signalix_pass/' .env
echo "Aligned to signalix_pass. count:"; grep -c '^POSTGRES_PASSWORD=signalix_pass$' .env
