"""Read-only integration check of the already completed Apify comments run."""
import os
from datetime import date
from build_rss import initial_state, sync_existing_comments_run, build_week_data, rss_xml
from datetime import datetime, timezone

token = os.environ.get("APIFY_TOKEN", "").strip()
if not token:
    raise SystemExit("APIFY_TOKEN unavailable: real dataset test not run")
state = initial_state()
result = sync_existing_comments_run(state, token)
week = build_week_data(state, date(2026, 10, 19))
assert week["new_comment_count"] >= 1, "No comment found in S43"
assert week["new_post_count"] == 0, "Placeholder incorrectly counted as a new post"
assert any("1601080907921988" in p.get("comments", {}) for p in state["posts"].values()), "Expected comment missing"
rss = rss_xml([week], "https://example.invalid/", datetime.now(timezone.utc)).decode("utf-8")
assert "1601080907921988" in rss, "Comment missing from RSS"
print("S43 integration OK:", result["comments_added"], "comments imported; RSS includes expected comment")
