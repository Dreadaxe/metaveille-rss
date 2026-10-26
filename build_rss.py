#!/usr/bin/env python3
"""MetaVeille RSS Auto: archives completed Apify datasets, publishes a weekly RSS digest.
Only GET calls. Never triggers a paid Apify run. Python 3.11+, stdlib only.
"""
from __future__ import annotations

import argparse
import copy
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
from import_comments import merge_comments_dataset

GROUP_ID = '309721797057912'
GROUP_URL = 'https://www.facebook.com/groups/309721797057912/'
GROUP_NAME = 'Groupe Facebook Warhammer Quest Fr'
ACTOR_ID = '2chN8UQcH1CfxLRNE'  # Actor officiel utilisé par le run déjà vérifié
COMMENTS_ACTOR_ID = 'us5srxAYnsrkgUv2v'  # Facebook Comments Scraper; read completed runs only
TZ = ZoneInfo('Europe/Paris')
ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'data' / 'state.json'
SITE = ROOT / 'site'
MAX_RUNS = 35
RSS_WEEKS = 12
MAX_ITEMS_PER_DATASET = 300


def when(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.astimezone(TZ) if dt.tzinfo else None
    except (ValueError, TypeError):
        return None


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def safe_url(value):
    try:
        parts = urllib.parse.urlsplit(str(value or ''))
        host = (parts.hostname or '').lower()
        if parts.scheme == 'https' and (host == 'facebook.com' or host.endswith('.facebook.com')):
            return str(value)
    except ValueError:
        pass
    return ''


def esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)


def flat(value, limit=220):
    s = ' '.join(str(value or '').split())
    return s if len(s) <= limit else s[:limit].rsplit(' ', 1)[0] + '…'


def valid_group(item):
    if str(item.get('facebookId') or '') == GROUP_ID:
        return True
    for key in ('facebookUrl', 'inputUrl'):
        url = str(item.get(key) or '').lower()
        if ('/groups/' + GROUP_ID) in url or '/groups/warhammerquestfr' in url:
            return True
    return False


def post_key(item):
    val = item.get('legacyId') or item.get('id')
    if val:
        return str(val)
    url = str(item.get('url') or '')
    match = re.search(r'/(?:permalink|posts)/(\d+)', url)
    return match.group(1) if match else ''


def comment_key(comment):
    cid = comment.get('commentId') or comment.get('id')
    if cid:
        return str(cid)
    link = str(comment.get('commentUrl') or '')
    match = re.search(r'comment_id=(\d+)', link)
    return match.group(1) if match else ''


def extract_reactions(item):
    mapping = {'like': 'reactionLikeCount', 'love': 'reactionLoveCount', 'care': 'reactionCareCount',
               'haha': 'reactionHahaCount', 'wow': 'reactionWowCount', 'sad': 'reactionSadCount', 'angry': 'reactionAngryCount'}
    result = {}
    for label, key in mapping.items():
        v = item.get(key)
        if isinstance(v, int) and v >= 0:
            result[label] = v
    return result


def as_count(item, key):
    value = item.get(key)
    return value if isinstance(value, int) and value >= 0 else None


def initial_state():
    return {'schema': 1, 'runs': {}, 'posts': {}, 'updated_at': ''}


def load_state(path=STATE):
    if not path.exists():
        return initial_state()
    state = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(state, dict) or state.get('schema') != 1 or not isinstance(state.get('posts'), dict):
        raise ValueError('Archive MetaVeille invalide, arrêt sans écrasement.')
    if not isinstance(state.get('runs'), dict):
        raise ValueError('Liste des exécutions invalide.')
    return state


def merge_dataset(state, items, captured_at, run_id):
    created_posts = 0
    created_comments = 0
    for item in items:
        if not isinstance(item, dict) or not valid_group(item):
            continue
        key = post_key(item)
        url = safe_url(item.get('url'))
        if not key or not url:
            continue
        owner = item.get('user') if isinstance(item.get('user'), dict) else {}
        record = state['posts'].get(key)
        if record is None:
            record = {'id': key, 'first_seen': captured_at, 'comments': {}}
            state['posts'][key] = record
            created_posts += 1
        record.update({
            'url': url, 'author': str(owner.get('name') or record.get('author') or 'Auteur non identifié'),
            'published_at': item.get('time') or record.get('published_at') or '',
            'body': item.get('text') if item.get('text') is not None else record.get('body') or '',
            'last_seen': captured_at, 'last_run_id': run_id,
            'reactions': as_count(item, 'likesCount'),
            'reaction_breakdown': extract_reactions(item),
            'comments_count': as_count(item, 'commentsCount'),
            'shares_count': as_count(item, 'sharesCount'),
            'media_count': len(item.get('attachments') or []) if isinstance(item.get('attachments'), list) else 0,
        })
        for c in item.get('topComments') or []:
            if not isinstance(c, dict):
                continue
            cid = comment_key(c)
            if not cid:
                continue
            author = c.get('author') if isinstance(c.get('author'), dict) else {}
            comment_url = safe_url(c.get('commentUrl')) or url
            old = record['comments'].get(cid, {'id': cid, 'first_seen': captured_at})
            if cid not in record['comments']:
                created_comments += 1
            old.update({'url': comment_url, 'author': str(c.get('profileName') or author.get('name') or old.get('author') or 'Auteur inconnu'),
                        'text': c.get('text') if c.get('text') is not None else old.get('text') or '',
                        'published_at': c.get('date') or old.get('published_at') or '',
                        'likes_count': as_count(c, 'likesCount'), 'last_seen': captured_at})
            record['comments'][cid] = old
    return created_posts, created_comments


class NoOffsiteRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        dest = urllib.parse.urlsplit(newurl)
        if dest.scheme != 'https' or dest.hostname != 'api.apify.com':
            raise RuntimeError('Redirection hors de api.apify.com refusée.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def api_json(path, token):
    if not token:
        raise RuntimeError('Secret APIFY_TOKEN absent. Aucun accès aux exécutions privées.')
    if not path.startswith('/v2/') or '..' in path:
        raise ValueError('Chemin Apify invalide.')
    opener = urllib.request.build_opener(NoOffsiteRedirect())
    req = urllib.request.Request('https://api.apify.com' + path,
                                headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json',
                                         'User-Agent': 'MetaVeille-RSS-Auto/1.0'})
    for attempt in range(3):
        try:
            with opener.open(req, timeout=40) as response:
                content = response.read(12 * 1024 * 1024 + 1)
            if len(content) > 12 * 1024 * 1024:
                raise RuntimeError('Réponse trop volumineuse.')
            return json.loads(content.decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError('Dataset Apify expiré ou inaccessible.') from exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f'API Apify: erreur HTTP {exc.code}.') from exc
            time.sleep(1 + 2 * attempt)
        except urllib.error.URLError as exc:
            if attempt == 2:
                raise RuntimeError('API Apify temporairement inaccessible.') from exc
            time.sleep(1 + 2 * attempt)


def fetch_runs(token, limit=MAX_RUNS):
    args = urllib.parse.urlencode({'status': 'SUCCEEDED', 'desc': '1', 'limit': min(limit, 100)})
    # The user-run endpoint is reliable even for Store Actors owned by Apify.
    response = api_json('/v2/actor-runs?' + args, token)
    data = response.get('data') or {}
    return [run for run in data.get('items') or [] if str(run.get('actId') or '') == ACTOR_ID]


def sync_apify(state, token, now=None):
    now = now or datetime.now(timezone.utc)
    runs = fetch_runs(token)
    changes = {'runs_imported': 0, 'new_posts': 0, 'new_comments': 0, 'expired': 0}
    # oldest first yields correct last-seen snapshots.
    for run in sorted(runs, key=lambda x: x.get('startedAt') or ''):
        rid = str(run.get('id') or '')
        if not rid or rid in state['runs'] or run.get('status') != 'SUCCEEDED':
            continue
        finished = when(run.get('finishedAt'))
        if finished is None:
            continue
        age = now - finished.astimezone(timezone.utc)
        if age > timedelta(days=15):
            # Probably expired on Apify Free; do not make a doomed API call.
            continue
        dataset_id = str(run.get('defaultDatasetId') or '')
        if not re.fullmatch(r'[a-zA-Z0-9]+', dataset_id):
            continue
        try:
            query = urllib.parse.urlencode({'format': 'json', 'limit': MAX_ITEMS_PER_DATASET, 'offset': 0})
            items = api_json('/v2/datasets/' + dataset_id + '/items?' + query, token)
        except FileNotFoundError:
            changes['expired'] += 1
            continue
        if not isinstance(items, list):
            raise RuntimeError('Format des publications Apify invalide.')
        new_p, new_c = merge_dataset(state, items, run.get('finishedAt') or utc_now(), rid)
        state['runs'][rid] = {'finished_at': run.get('finishedAt') or '', 'items_read': len(items),
                              'posts_added': new_p, 'comments_added': new_c}
        changes['runs_imported'] += 1
        changes['new_posts'] += new_p
        changes['new_comments'] += new_c
    state['updated_at'] = utc_now()
    return changes


def fetch_comments_runs(token, limit=100):
    """Discover successful Comments Scraper runs using GET only."""
    args = urllib.parse.urlencode({'status': 'SUCCEEDED', 'desc': '1', 'limit': min(limit, 100)})
    response = api_json('/v2/actor-runs?' + args, token)
    data = response.get('data') or {}
    return [run for run in data.get('items') or []
            if str(run.get('actId') or '') == COMMENTS_ACTOR_ID
            and run.get('status') == 'SUCCEEDED']


def sync_comments_runs(state, token, now=None):
    """Import recent completed comment runs once; never start a paid run."""
    now = now or datetime.now(timezone.utc)
    tracked = state.setdefault('comment_runs', {})
    result = {'runs_imported': 0, 'comments_added': 0, 'comments_updated': 0}
    runs = fetch_comments_runs(token)
    for run in sorted(runs, key=lambda r: r.get('finishedAt') or ''):
        rid = str(run.get('id') or '')
        if not rid or rid in tracked:
            continue
        finished = when(run.get('finishedAt'))
        if finished is None or now - finished.astimezone(timezone.utc) > timedelta(days=15):
            continue
        dataset_id = str(run.get('defaultDatasetId') or '')
        if not re.fullmatch(r'[a-zA-Z0-9]+', dataset_id):
            continue
        query = urllib.parse.urlencode({'format': 'json', 'limit': MAX_ITEMS_PER_DATASET, 'offset': 0})
        try:
            items = api_json('/v2/datasets/' + dataset_id + '/items?' + query, token)
        except FileNotFoundError:
            continue
        if not isinstance(items, list):
            raise RuntimeError('Format du dataset de commentaires invalide.')
        merged = merge_comments_dataset(state, items, run.get('finishedAt') or utc_now())
        tracked[rid] = {'items_read': len(items), **merged}
        result['runs_imported'] += 1
        result['comments_added'] += merged['comments_added']
        result['comments_updated'] += merged['comments_updated']
    return result


def sync_existing_comments_run(state, token, run_id='7q4GdkJQrvbNCXj0v'):
    """Read a completed comments run; never start an Actor or incur run charges."""
    if run_id in state.setdefault('comment_runs', {}):
        return {'already_imported': True, 'comments_added': 0}
    response = api_json('/v2/actor-runs/' + urllib.parse.quote(run_id, safe=''), token)
    run = response.get('data') or {}
    if run.get('status') != 'SUCCEEDED':
        raise RuntimeError('Exécution de commentaires non terminée avec succès.')
    dataset_id = str(run.get('defaultDatasetId') or '')
    if not re.fullmatch(r'[a-zA-Z0-9]+', dataset_id):
        raise RuntimeError('Dataset de commentaires absent.')
    query = urllib.parse.urlencode({'format': 'json', 'limit': MAX_ITEMS_PER_DATASET, 'offset': 0})
    items = api_json('/v2/datasets/' + dataset_id + '/items?' + query, token)
    if not isinstance(items, list):
        raise RuntimeError('Format du dataset de commentaires invalide.')
    result = merge_comments_dataset(state, items, run.get('finishedAt') or utc_now())
    state['comment_runs'][run_id] = {'items_read': len(items), **result}
    return result


def week_start(today):
    if isinstance(today, datetime):
        today = today.astimezone(TZ).date()
    return today - timedelta(days=today.weekday())


def build_week_data(state, start):
    finish = start + timedelta(days=7)
    entries = []
    nnew_posts = 0
    nnew_comments = 0
    for p in state['posts'].values():
        p_dt = when(p.get('published_at')) or (None if p.get('placeholder') else when(p.get('first_seen')))
        comments = []
        for c in p.get('comments', {}).values():
            dt = when(c.get('published_at')) or when(c.get('first_seen'))
            if dt and start <= dt.date() < finish:
                comments.append(c)
        comments.sort(key=lambda c: c.get('published_at') or c.get('first_seen') or '')
        is_new = bool(p_dt and start <= p_dt.date() < finish)
        if is_new or comments:
            nnew_posts += int(is_new)
            nnew_comments += len(comments)
            entries.append({'post': p, 'comments': comments, 'is_new': is_new})
    entries.sort(key=lambda e: e['post'].get('published_at') or e['post'].get('first_seen') or '', reverse=True)
    iso_y, iso_w, _ = start.isocalendar()
    return {'start': start, 'end': finish - timedelta(days=1), 'year': iso_y, 'week': iso_w,
            'posts': entries, 'new_post_count': nnew_posts, 'new_comment_count': nnew_comments}


def heading(info):
    d0 = info['start'].strftime('%d/%m/%Y')
    d1 = info['end'].strftime('%d/%m/%Y')
    return f'{GROUP_NAME} — Semaine {info["week"]} — Bilan du {d0} au {d1}'


def week_filename(info):
    return f'semaine-{info["year"]}-S{info["week"]:02d}.html'


def html_card(entry, n):
    p = entry['post']
    title = flat(p.get('body') or ('Publication d’origine non archivée' if p.get('placeholder') else 'Publication sans texte'), 90)
    stats = []
    if isinstance(p.get('reactions'), int):
        bits = []
        emojis = {'like': '👍', 'love': '❤️', 'care': '🥰', 'haha': '😆', 'wow': '😮', 'sad': '😢', 'angry': '😠'}
        for k, icon in emojis.items():
            if (v := p.get('reaction_breakdown', {}).get(k)) is not None and v > 0:
                bits.append(f'{icon} {v}')
        reaction = f'{p["reactions"]} réactions'
        if bits:
            reaction += ' (' + ' · '.join(bits) + ')'
        stats.append(reaction)
    if isinstance(p.get('comments_count'), int):
        stats.append(f'{p["comments_count"]} commentaires sur Facebook')
    if isinstance(p.get('shares_count'), int):
        stats.append(f'{p["shares_count"]} partages')
    details = ''
    if entry['comments']:
        rows = []
        for c in entry['comments']:
            url = safe_url(c.get('url')) or safe_url(p.get('url'))
            rows.append(f'<li><b>{esc(c.get("author"))}</b> — {esc(c.get("text"))}' +
                        (f' <a href="{esc(url)}" rel="noopener noreferrer" target="_blank">Voir le commentaire ↗</a>' if url else '') + '</li>')
        details = (f'<details><summary>Voir les {len(rows)} commentaires récupérés pour cette semaine</summary>'
                   f'<ol class="comments">{"".join(rows)}</ol></details>')
    fb = safe_url(p.get('url'))
    media_link = (f'<a class="media" href="{esc(fb)}" target="_blank" rel="noopener noreferrer">'
                  f'Voir les {p.get("media_count")} médias sur Facebook ↗</a>' if p.get('media_count') and fb else '')
    return (f'<article class="post" id="p{n}"><div class="byline"><b>{esc(p.get("author"))}</b>'
            f' <small>{esc((p.get("published_at") or "")[:10])}</small></div>'
            f'<h3>{esc(title)}</h3><p class="body">{esc(p.get("body") or "")}</p>'
            f'<p class="metrics">{" · ".join(esc(s) for s in stats)}</p>'
            f'{details}{media_link} <a class="open" href="{esc(fb)}" target="_blank" rel="noopener noreferrer">Ouvrir sur Facebook ↗</a></article>')


CSS = '''*{box-sizing:border-box}body{font:15px/1.55 system-ui,Segoe UI,sans-serif;color:#20334a;background:#f4f6fa;margin:0}
main{max-width:1150px;padding:24px 16px;margin:auto}h1{line-height:1.3;font-size:25px}h2{font-size:20px}a{color:#2359a4}
header{padding:0 0 15px}header p{color:#52627a}.index{background:#fff;border:1px solid #dce3ee;border-radius:14px;padding:18px 20px;margin-bottom:22px}
.index ol{padding-left:24px}.index li{padding:5px 0}.cardgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.post{min-width:0;background:#fff;border:1px solid #dce4ee;border-radius:14px;padding:19px;box-shadow:0 2px 10px #1427490a}
.post h3{font-size:17px;margin:12px 0}.body{white-space:pre-wrap;overflow-wrap:anywhere;max-height:320px;overflow:auto}
.metrics,.byline small,.footnote{font-size:12px;color:#697b92}.metrics{border-top:1px solid #e1eaf3;padding-top:10px}
details{background:#f2f6fc;border-radius:9px;padding:10px;margin:10px 0}summary{cursor:pointer;font-weight:700;color:#2455a0}
.comments{padding-left:25px;overflow-wrap:anywhere}.comments li{margin:9px 0}.open{display:inline-block;font-weight:700;margin-top:7px}
@media(max-width:700px){.cardgrid{grid-template-columns:1fr}.post{padding:14px}}'''


def document(info, base_url):
    title = heading(info)
    links = []
    cards = []
    for idx, entry in enumerate(info['posts'], 1):
        p = entry['post']
        links.append(f'<li><a href="#p{idx}">{esc(flat(p.get("body") or ("Publication d’origine non archivée" if p.get("placeholder") else "Publication sans texte"), 115))}</a>'
                     f' <small>— {esc(p.get("author"))}</small></li>')
        cards.append(html_card(entry, idx))
    if not links:
        links.append('<li>Aucune publication ou nouveau commentaire retrouvé dans les données archivées pour cette semaine.</li>')
    return (f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)}</title><link rel="alternate" type="application/rss+xml" title="MetaVeille RSS" href="{esc(base_url)}rss.xml">'
            f'<style>{CSS}</style></head><body><main><header><h1>{esc(title)}</h1>'
            f'<p>{info["new_post_count"]} publications datées de la semaine · {info["new_comment_count"]} commentaires récupérés · '
            f'<a href="{esc(base_url)}rss.xml">S’abonner au RSS</a></p></header>'
            f'<nav class="index"><h2>PUBLICATIONS — Title-Only</h2><ol>{"".join(links)}</ol></nav>'
            f'<section><h2>Card view — Publications et commentaires</h2><div class="cardgrid">{"".join(cards)}</div></section>'
            f'<p class="footnote">Commentaires : sélection partielle, pas la totalité des échanges. '
            f'Données collectées sans garantie d’exhaustivité. Respecter les autorisations de repartage.</p>'
            f'</main></body></html>')


def rss_summary(info):
    lines = ['<p>Publications et commentaires collectés au cours de la semaine.</p>', '<ol>']
    for entry in info['posts']:
        p = entry['post']
        url = safe_url(p.get('url'))
        lines.append(f'<li><b>{esc(p.get("author"))}</b> — <a href="{esc(url)}">{esc(flat(p.get("body") or ("Publication d’origine non archivée" if p.get("placeholder") else "Publication sans texte"), 175))}</a>')
        if entry['comments']:
            lines.append('<ul>')
            for c in entry['comments']:
                curl = safe_url(c.get('url')) or url
                lines.append(f'<li>— <b>{esc(c.get("author"))}</b> — '
                             f'<a href="{esc(curl)}">{esc(flat(c.get("text"), 130))}</a></li>')
            lines.append('</ul>')
        lines.append('</li>')
    lines.append('</ol><p>Commentaires : sélection partielle, pas la totalité des échanges.</p>')
    return ''.join(lines)


def rss_xml(weeks, base_url, built_at):
    rss = ET.Element('rss', {'version': '2.0'})
    channel = ET.SubElement(rss, 'channel')
    for k, v in [('title', 'MetaVeille — Groupe Facebook Warhammer Quest Fr — Bilans hebdomadaires'),
                 ('link', base_url), ('description', 'Un bilan hebdomadaire des nouvelles publications et commentaires retrouvés sur Facebook.'),
                 ('language', 'fr-FR'), ('lastBuildDate', built_at.strftime('%a, %d %b %Y %H:%M:%S +0000'))]:
        ET.SubElement(channel, k).text = v
    for info in weeks:
        item = ET.SubElement(channel, 'item')
        fname = week_filename(info)
        for k, v in [('title', heading(info)), ('link', base_url + fname),
                     ('guid', 'metaveille-' + str(info['year']) + '-W' + f'{info["week"]:02d}'),
                     ('description', rss_summary(info))]:
            child = ET.SubElement(item, k)
            if k == 'guid':
                child.set('isPermaLink', 'false')
            child.text = v
        t = datetime.combine(info['end'] + timedelta(days=1), datetime.min.time(), TZ)
        pub = t.astimezone(timezone.utc)
        ET.SubElement(item, 'pubDate').text = pub.strftime('%a, %d %b %Y %H:%M:%S +0000')
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(rss, encoding='utf-8')


def site_url():
    explicit = os.environ.get('PUBLIC_BASE_URL', '').strip()
    if explicit:
        if not explicit.startswith('https://'):
            raise ValueError('PUBLIC_BASE_URL doit commencer par https://')
        return explicit.rstrip('/') + '/'
    repo = os.environ.get('GITHUB_REPOSITORY', 'exemple/MetaVeille-RSS')
    if '/' not in repo:
        raise ValueError('Nom de dépôt GitHub incorrect.')
    account, slug = repo.split('/', 1)
    return f'https://{account.lower()}.github.io/{slug}/'


def make_site(state, today=None, base_url=None):
    today = today or datetime.now(TZ).date()
    base_url = base_url or site_url()
    SITE.mkdir(exist_ok=True, parents=True)
    # Only COMPLETED weeks become RSS items; newest first.
    first = week_start(today) - timedelta(days=7)
    weeks = [build_week_data(state, first - timedelta(weeks=i)) for i in range(RSS_WEEKS)]
    files = []
    for info in weeks:
        if not info['posts']:
            continue  # No fabricated activity for empty weeks.
        name = week_filename(info)
        (SITE / name).write_text(document(info, base_url), encoding='utf-8')
        files.append((name, info))
    # Only feed real weeks with observed posts / comments.
    published_weeks = [info for name, info in files]
    built = datetime.now(timezone.utc)
    (SITE / 'rss.xml').write_bytes(rss_xml(published_weeks, base_url, built))
    links = ''.join(f'<li><a href="{esc(name)}">{esc(heading(info))}</a> — '
                    f'{info["new_post_count"]} publications, {info["new_comment_count"]} commentaires récupérés</li>'
                    for name, info in files)
    (SITE / 'index.html').write_text('<!doctype html><html lang="fr"><head><meta charset="utf-8">'
          '<meta name="viewport" content="width=device-width,initial-scale=1">'
          '<title>MetaVeille — Bilans Groupe Facebook Warhammer Quest Fr</title><style>' + CSS + '</style></head><body><main>'
          '<h1>MetaVeille — Bilans hebdomadaires</h1><p><a href="rss.xml">S’abonner au flux RSS ↗</a></p>'
          '<ul>' + (links or '<li>Première publication en attente.</li>') + '</ul>'
          '<p>Commentaires : sélection partielle, pas la totalité des échanges.</p></main></body></html>',
          encoding='utf-8')
    (SITE / '.nojekyll').write_text('', encoding='utf-8')
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true', help='Générer à partir du fichier data/state.json, sans accès Apify')
    parser.add_argument('--seed-json', type=Path, help='Test local: fusionner un export Apify de démonstration')
    parser.add_argument('--today', help='Date ISO YYYY-MM-DD pour test')
    args = parser.parse_args()
    state = load_state()
    if args.seed_json:
        items = json.loads(args.seed_json.read_text(encoding='utf-8'))
        if not isinstance(items, list):
            raise ValueError('Export Apify invalide')
        print('Données de test:', merge_dataset(state, items, utc_now(), 'test-local'))
    if not args.offline:
        token = os.environ.get('APIFY_TOKEN', '').strip()
        changes = sync_apify(state, token)
        print('Synchronisation:', changes)
        print('Commentaires (runs terminés):', sync_comments_runs(state, token))
    d = date.fromisoformat(args.today) if args.today else datetime.now(TZ).date()
    files = make_site(state, today=d)
    # Only save an archive successfully synchronized or deliberately seeded/offline.
    STATE.parent.mkdir(exist_ok=True, parents=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(STATE)
    print('Bilan(s):', len(files), 'flux RSS:', SITE / 'rss.xml')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('MetaVeille RSS : erreur —', exc, file=sys.stderr)
        raise SystemExit(1)
