"""Standalone Signalix real-time delivery consumer.

Subscribes to the Redis `signals` channel and fans out every envelope to
Telegram + LINE. Runs as its own process so the FastAPI backend only has to
PUBLISH; this keeps webhook ingest fast and isolates delivery failures.

Run:
    python delivery_consumer.py
(or via the provided systemd unit delivery_consumer.service)
"""
from delivery import run_consumer

if __name__ == "__main__":
    run_consumer()
