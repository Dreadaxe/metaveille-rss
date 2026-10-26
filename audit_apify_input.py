#!/usr/bin/env python3
"""Read-only, redacted inspection of an existing Apify Posts Actor run input."""
import json
import os
import urllib.parse
from build_rss import ACTOR_ID, api_json

SAFE_KEYS = ("resultsLimit", "maxPosts", "maxItems", "sort", "sorting", "sortBy",
             "viewOption", "onlyPostsNewerThan", "startDate", "endDate")


def redact_input(value):
    if not isinstance(value, dict):
        return {"available": False}
    settings = {key: value[key] for key in SAFE_KEYS
                if key in value and (value[key] is None or type(value[key]) in (str, int, float, bool))}
    for key in ("startUrls", "urls", "groupUrls"):
        if isinstance(value.get(key), list):
            settings[key + "_count"] = len(value[key])
            settings[key + "_hosts"] = sorted({
                urllib.parse.urlsplit(str(v.get("url", "") if isinstance(v, dict) else v)).hostname or ""
                for v in value[key]
            })
    return {"available": True, "settings": settings, "field_names": sorted(value.keys())}


def inspect(token):
    q = urllib.parse.urlencode({"status": "SUCCEEDED", "desc": "1", "limit": 100})
    data = api_json("/v2/actor-runs?" + q, token).get("data") or {}
    runs = [r for r in data.get("items") or [] if str(r.get("actId") or "") == ACTOR_ID]
    if not runs:
        raise RuntimeError("Aucun run Posts Actor trouvé")
    run = max(runs, key=lambda r: r.get("finishedAt") or "")
    run_id = str(run.get("id") or "")
    if not run_id.isalnum():
        raise RuntimeError("ID run invalide")
    # Existing run input; never trigger an Actor.
    raw = api_json("/v2/actor-runs/" + run_id + "/input", token)
    return run_id, redact_input(raw)


if __name__ == "__main__":
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise SystemExit("APIFY_TOKEN absent")
    run_id, result = inspect(token)
    report = "### Entrée du dernier run Posts Actor (lecture seule)\n\n" + (
        "Run : `" + run_id + "`\n\n"
        + "```json\n" + json.dumps(result, indent=2, ensure_ascii=False) + "\n```\n"
    )
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report)
