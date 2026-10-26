"""Import Facebook Comments Scraper datasets into MetaVeille's archive.

Offline-only helper. No Apify requests and no paid Actor runs.
Use this on the feature branch before wiring it into build_rss.py.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, parse_qs


def _post_id(item):
    value = str(item.get("facebookId") or "")
    if value.isdigit():
        return value
    for field in ("facebookUrl", "inputUrl", "commentUrl"):
        match = re.search(r"/(?:posts|permalink)/(\d+)", str(item.get(field) or ""))
        if match:
            return match.group(1)
    return ""


def _comment_id(item):
    value = str(item.get("commentId") or "")
    if value.isdigit():
        return value
    url = str(item.get("commentUrl") or "")
    return (parse_qs(urlsplit(url).query).get("comment_id") or [""])[0]


def merge_comments_dataset(state, items, captured_at):
    """Merge a comments Actor dataset. Return counts; don't fabricate parent metadata."""
    added = 0
    updated = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        post_id, cid = _post_id(item), _comment_id(item)
        url = str(item.get("commentUrl") or "")
        parent_url = str(item.get("facebookUrl") or item.get("inputUrl") or "")
        if not post_id or not cid or not url.startswith("https://www.facebook.com/groups/"):
            continue
        if not (parent_url.startswith("https://www.facebook.com/groups/warhammerquestfr/") or parent_url.startswith("https://www.facebook.com/groups/309721797057912/")):
            continue
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        posts = state.setdefault("posts", {})
        if post_id not in posts:
            posts[post_id] = {
                "id": post_id,
                "url": parent_url,
                "author": "Auteur de la publication non identifié",
                "published_at": "",
                "body": "",
                "first_seen": captured_at,
                "last_seen": captured_at,
                "placeholder": True,
                "comments": {},
            }
        post = posts[post_id]
        comments = post.setdefault("comments", {})
        old = comments.get(cid, {"id": cid, "first_seen": captured_at})
        if cid in comments:
            updated += 1
        else:
            added += 1
        likes = item.get("likesCount")
        old.update({
            "url": url,
            "author": str(item.get("profileName") or author.get("name") or old.get("author") or "Auteur inconnu"),
            "text": str(item.get("text") or old.get("text") or ""),
            "published_at": str(item.get("date") or old.get("published_at") or ""),
            "likes_count": int(likes) if str(likes).isdigit() else None,
            "last_seen": captured_at,
            "threading_depth": item.get("threadingDepth"),
        })
        comments[cid] = old
    return {"comments_added": added, "comments_updated": updated}
