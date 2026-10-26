#!/usr/bin/env python3
"""Start the configured Apify comments task at most once per Paris ISO week.

This script is the ONLY MetaVeille component that starts a paid Apify run.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TASK_ID = os.environ.get("APIFY_COMMENTS_TASK_ID", "dreadaxe~metaveille-commentaires-wqfr")
BASE = "https://api.apify.com/v2/actor-tasks/" + urllib.parse.quote(TASK_ID, safe="~")
TZ = ZoneInfo("Europe/Paris")


def request(path, token, method="GET"):
    req = urllib.request.Request(BASE + path, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "MetaVeille-Weekly-Comments/1.0",
    })
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp).get("data") or {}


def run_once(token, now=None):
    now = now or datetime.now(TZ)
    local = now.astimezone(TZ)
    start = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    # Check all task runs (including failed and in-progress), not only successes.
    data = request("/runs?desc=1&limit=100", token)
    for run in data.get("items", []):
        raw = run.get("startedAt")
        if not raw:
            continue
        started = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TZ)
        if started >= start:
            print("Collecte déjà lancée cette semaine:", run.get("id"), run.get("status"))
            return False
    # No previous run this week: a new execution may incur Apify charges.
    run = request("/runs", token, method="POST")
    print("Nouvelle collecte lancée:", run.get("id"), run.get("status"))
    return True


if __name__ == "__main__":
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise SystemExit("Secret APIFY_TOKEN absent")
    run_once(token)
