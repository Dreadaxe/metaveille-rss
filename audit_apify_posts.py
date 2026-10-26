#!/usr/bin/env python3
"""Read-only audit of the latest existing Apify Facebook-posts dataset."""
import json
import os
import urllib.parse
from datetime import datetime, timezone
from build_rss import ACTOR_ID, MAX_ITEMS_PER_DATASET, api_json, post_key, valid_group, safe_url, when


def summarize(items, now=None):
    now = now or datetime.now(timezone.utc)
    dates = []
    rejected = {"wrong_group": 0, "missing_id": 0, "unsafe_url": 0}
    ids = set()
    accepted = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if not valid_group(item):
            rejected["wrong_group"] += 1
            continue
        pid = post_key(item)
        if not pid:
            rejected["missing_id"] += 1
            continue
        if not safe_url(item.get("url")):
            rejected["unsafe_url"] += 1
            continue
        accepted += 1
        ids.add(pid)
        stamp = when(item.get("time"))
        if stamp:
            dates.append(stamp)
    newest = max(dates, default=None)
    return {
        "dataset_items": len(items),
        "accepted": accepted,
        "unique_ids": len(ids),
        "rejected": rejected,
        "newest_post": newest.isoformat() if newest else None,
        "newest_age_days": round((now - newest.astimezone(timezone.utc)).total_seconds() / 86400, 1) if newest else None,
        "post_ids": ids,
    }


def audit(token):
    # Only GET requests: inspect the existing most recent successful run.
    query = urllib.parse.urlencode({"status": "SUCCEEDED", "desc": "1", "limit": 100})
    data = api_json("/v2/actor-runs?" + query, token).get("data") or {}
    runs = [r for r in data.get("items") or [] if str(r.get("actId") or "") == ACTOR_ID]
    if not runs:
        raise RuntimeError("Aucune exécution réussie de l'Actor publications trouvée.")
    run = max(runs, key=lambda r: r.get("finishedAt") or "")
    rid = str(run.get("id") or "")
    dataset = str(run.get("defaultDatasetId") or "")
    if not dataset.isalnum():
        raise RuntimeError("Identifiant du dataset invalide.")
    query = urllib.parse.urlencode({"format": "json", "limit": MAX_ITEMS_PER_DATASET, "offset": 0})
    items = api_json("/v2/datasets/" + dataset + "/items?" + query, token)
    if not isinstance(items, list):
        raise RuntimeError("Format du dataset invalide.")
    result = summarize(items)
    result["run_id"] = rid
    result["finished_at"] = run.get("finishedAt")
    result["dataset_id"] = dataset
    return result


def render(report):
    lines = [
        "### Audit Apify — publications (lecture seule)",
        f"- Run : \`{report['run_id']}\`",
        f"- Terminé : {report['finished_at']}",
        f"- Éléments du dataset : {report['dataset_items']}",
        f"- Acceptés par MetaVeille : {report['accepted']}",
        f"- Identifiants uniques : {report['unique_ids']}",
        f"- Rejetés (autre groupe) : {report['rejected']['wrong_group']}",
        f"- Rejetés (identifiant manquant) : {report['rejected']['missing_id']}",
        f"- Rejetés (URL invalide) : {report['rejected']['unsafe_url']}",
        f"- Publication la plus récente dans le dataset : {report['newest_post'] or 'inconnue'}",
        f"- Ancienneté : {report['newest_age_days']} jours",
        "",
        "Ce diagnostic ne lance aucun Actor et ne modifie aucune tâche Apify.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise SystemExit("Secret APIFY_TOKEN absent")
    result = audit(token)
    report = render(result)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(report)
