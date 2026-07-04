"""Shared, cached API client instances.

Constructing a fresh client per task (or per poll retry) leaks its keep-alive
connection pool — one or more sockets each — until the Celery worker exhausts
its open-file limit and every task starts failing with EMFILE. Clients are
cached per credential so a runtime credential change (via the settings
endpoint) still picks up a new client, while repeat calls reuse one pool.
"""
from functools import lru_cache

from apify_client import ApifyClient


@lru_cache(maxsize=8)
def get_apify_client(token):
    return ApifyClient(token)
