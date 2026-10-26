#!/usr/bin/env python3
"""Launch at most one paid Apify comments task per Paris ISO week.

Targets recent posts already archived by MetaVeille; no discovery of unseen posts.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TASK_ID = (os.environ.get("APIFY_COMMENTS_TASK_ID") or "dreadaxe~metaveille-commentaires-wqfr")
BASE = "https://api.apify.com/v2/actor-tasks/" + urllib.parse.quote(TASK_ID, safe="~")
TZ = ZoneInfo("Europe/Paris")
STATE_PATH = Path(__file__).resolve().parent / "data" / "state.json"
MAX_POSTS = 12
LOOKBACK_DAYS = 21


def request(path, token, method="GET", payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MetaVeille-Weekly-Comments/1.1",
    })
    with urllib.request.urlopen(req, timeout=45) as resp:
        value = json.load(resp)
        return value.get("data", value) if isinstance(value, dict) else value


def select_posts(state, now):
    """Prefer recently published posts, then recent observed comment activity."""
    cutoff = now - timedelta(days=LOOKBACK_DAYS)
    candidates = []
    for post in state.get("posts", {}).values():
        pid = str(post.get("id") or "")
        if not re.fullmatch(r"\d+", pid):
            continue
        url = str(post.get("url") or "")
        if not (url.startswith("https://www.facebook.com/groups/warhammerquestfr/")
                or url.startswith("https://www.facebook.com/groups/309721797057912/")):
            continue
        stamps = [post.get("published_at"), post.get("first_seen")]
        stamps += [c.get("published_at") for c in post.get("comments", {}).values()]
        dates = []
        for raw in stamps:
            try:
                if raw:
                    dates.append(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(TZ))
            except (ValueError, TypeError):
                continue
        if not dates or max(dates) < cutoff:
            continue
        # Canonical posts URL works for both /permalink/ and /posts/ archive links.
        candidates.append((max(dates), pid))
    candidates.sort(reverse=True)
    return [{"url": "https://www.facebook.com/groups/warhammerquestfr/posts/" + pid + "/"}
            for _, pid in candidates[:MAX_POSTS]]


def run_once(token, now=None, state_path=STATE_PATH):
    now = (now or datetime.now(TZ)).astimezone(TZ)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    runs = request("/runs?desc=1&limit=100", token)
    for run in runs.get("items", []):
        raw = run.get("startedAt")
        if not raw:
            continue
        started = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(TZ)
        if started >= week_start:
            print("Collecte déjà lancée cette semaine:", run.get("id"), run.get("status"))
            return False

    state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    urls = select_posts(state, now)
    if not urls:
        print("Aucune publication récente dans l'archive : collecte payante annulée.")
        return False

    task_input = request("/input", token)
    if not isinstance(task_input, dict):
        raise RuntimeError("Configuration de la tâche Apify inaccessible.")
    # Retain task options; only override target posts and the minimum comment date.
    task_input = dict(task_input)
    task_input["startUrls"] = urls
    task_input["onlyCommentsNewerThan"] = week_start.date().isoformat()
    print("Publications ciblées:", len(urls), "depuis", task_input["onlyCommentsNewerThan"])
    run = request("/runs", token, method="POST", payload=task_input)
    print("Nouvelle collecte lancée:", run.get("id"), run.get("status"))
    return True


if __name__ == "__main__":
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise SystemExit("Secret APIFY_TOKEN absent")
    run_once(token)
