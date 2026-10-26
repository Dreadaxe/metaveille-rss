#!/usr/bin/env python3
"""Read-only freshness diagnostic for MetaVeille's archived Facebook posts."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def parse_time(value):
    try:
        if value:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(PARIS)
    except (TypeError, ValueError):
        pass
    return None


def freshness(state, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(PARIS)
    posts = [p for p in state.get("posts", {}).values() if not p.get("placeholder")]
    dated = [(parse_time(p.get("published_at")), p) for p in posts]
    dated = [(dt, p) for dt, p in dated if dt]
    latest = max((dt for dt, _ in dated), default=None)
    latest_seen = max((parse_time(p.get("last_seen")) for p in posts if parse_time(p.get("last_seen"))), default=None)
    recent = sum(1 for dt, _ in dated if 0 <= (now - dt).total_seconds() <= 7 * 86400)
    days = (now - latest).total_seconds() / 86400 if latest else None
    return {
        "total_posts": len(posts),
        "dated_posts": len(dated),
        "published_last_7_days": recent,
        "latest_post": latest.isoformat() if latest else None,
        "latest_observed": latest_seen.isoformat() if latest_seen else None,
        "latest_post_age_days": round(days, 1) if days is not None else None,
        "stale": days is None or days > 7,
    }


def markdown(report):
    status = "⚠️ Publications potentiellement obsolètes" if report["stale"] else "✅ Publications récentes détectées"
    return ("### Fraîcheur des publications Facebook\\n"
            f"{status}\\n\\n"
            f"- Publications archivées : {report['total_posts']}\\n"
            f"- Publications datées des 7 derniers jours : {report['published_last_7_days']}\\n"
            f"- Date de la plus récente publication : {report['latest_post'] or 'inconnue'}\\n"
            f"- Âge de la plus récente publication : {report['latest_post_age_days']} jours\\n"
            f"- Dernière observation d'une publication : {report['latest_observed'] or 'inconnue'}\\n\\n"
            "Une exécution Apify récente ne prouve pas que les publications récupérées sont récentes.\\n")


if __name__ == "__main__":
    state = json.loads((Path(__file__).resolve().parent / "data/state.json").read_text(encoding="utf-8"))
    result = freshness(state)
    report = markdown(result).replace("\\n", "\n")
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(report + "\n")
    if result["stale"]:
        print("::warning::Les dernières publications archivées datent de plus de 7 jours.")
