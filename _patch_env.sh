#!/usr/bin/env bash
set -e
cd /root/signalix
grep -q '^DASHBOARD_PUBLIC_URL=' .env || printf 'DASHBOARD_PUBLIC_URL=http://91.98.72.120:3001\n' >> .env
grep -q '^TELEGRAM_CHAT_ID=' .env || printf 'TELEGRAM_CHAT_ID=\n' >> .env
echo "DASHBOARD_PUBLIC_URL lines: $(grep -c '^DASHBOARD_PUBLIC_URL=' .env)"
echo "TELEGRAM_CHAT_ID lines: $(grep -c '^TELEGRAM_CHAT_ID=' .env)"
echo "TELEGRAM_BOT_TOKEN lines: $(grep -c '^TELEGRAM_BOT_TOKEN=' .env)"
