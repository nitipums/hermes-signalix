#!/usr/bin/env bash
set -e
cd /root/signalix
# Align .env POSTGRES_PASSWORD with the ACTUAL postgres container password.
# The postgres volume was initialized with 'change_this_strong_password' and
# is NOT reset (we keep the 4.6M-row DB). So the env must match it.
if grep -q '^POSTGRES_PASSWORD=' .env; then
  sed -i 's/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=change_this_strong_password/' .env
else
  printf 'POSTGRES_PASSWORD=change_this_strong_password\n' >> .env
fi
echo "POSTGRES_PASSWORD aligned."
grep -c '^POSTGRES_PASSWORD=change_this_strong_password$' .env
