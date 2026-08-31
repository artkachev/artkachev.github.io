"""Сборка всех страниц сайта из site.json и data.json.

Готовый HTML здесь только пишется и никогда не разбирается обратно —
источник истины всегда данные, а не вёрстка.
"""
import html
import json
import re
from datetime import date
from pathlib import Path

import config
import theme

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

GENRE_LABELS = {
    "ru": {"ALL": "Все", "POP": "Поп", "HIPHOP": "Хип-хоп", "RAP": "Рэп",
           "INDIE": "Инди", "ROCK": "Рок", "ELECTRONIC": "Электроника",
           "DANCE": "Танцевальная", "ALT": "Альтернатива", "RNB": "R&B"},
    "en": {"ALL": "All", "POP": "Pop", "HIPHOP": "Hip-hop", "RAP": "Rap",
           "INDIE": "Indie", "ROCK": "Rock", "ELECTRONIC": "Electronic",
           "DANCE": "Dance", "ALT": "Alternative", "RNB": "R&B"},
}

WORDS = {
    "ru": {"works": "Работы", "all_tracks": "Все треки", "back": "← Все работы",
           "listen": "Слушать", "contact": "Связаться", "hub_title": "Все треки",
           "tracks_word": ("трек", "трека", "треков")},
    "en": {"works": "Works", "all_tracks": "All tracks", "back": "← All works",
           "listen": "Listen", "contact": "Get in touch", "hub_title": "All tracks",
           "tracks_word": ("track", "tracks", "tracks")},
}


def esc(s):
    return html.escape(str(s or ""), quote=True)


def slugify(*parts):
    text = " ".join(str(p) for p in parts).lower()
    out = "".join(TRANSLIT.get(ch, ch) for ch in text)
    out = re.sub(r"[^a-z0-9]+", "-", out)
    return out.strip("-")


def plural(n, forms):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def words(site):
    return WORDS.get(site["lang"], WORDS["ru"])


def genre_label(site, code):
    custom = site.get("genre_labels") or {}
    if code in custom:
        return custom[code]
    return GENRE_LABELS.get(site["lang"], GENRE_LABELS["ru"]).get(code, code)


def primary_role(site, roles):
    """Главная роль — первая по важности из объявленных в настройках."""
    for key in config.ROLE_ORDER:
        if key in (roles or []) and key in site["roles"]:
            return key
    return (roles or ["mix"])[0]


def order_releases(site, releases):
    visible = [r for r in releases if not r.get("hidden")]
    featured = list(site.get("featured") or [])

    def rank(rel):
        key = rel.get("id") or rel.get("album_id")
        return featured.index(key) if key in featured else len(featured)

    visible = sorted(visible, key=rank)
    by_artist = {}
    for rel in visible:
        by_artist.setdefault(rel["artist"], []).append(rel)
    ordered = []
    for artist in dict.fromkeys(r["artist"] for r in visible):
        ordered.extend(by_artist[artist])
    return ordered


# ── общие куски страницы ────────────────────────────────────────────

def head(site, *, title, description, canonical, image=None, extra=""):
    img = image or site.get("og_image")
    img_abs = img if not img or img.startswith("http") else f"{site['url']}{img}"
    ga = ""
    if site.get("analytics"):
        tag = esc(site["analytics"])
        ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={tag}"></script>'
              f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}'
              f'gtag("js",new Date());gtag("config","{tag}");</script>')
    og_img = f'<meta property="og:image" content="{esc(img_abs)}">' if img_abs else ""
    tw = "summary_large_image" if img_abs else "summary"
    return (
        f'<!doctype html><html lang="{esc(site["lang"])}"><head>'
        f'<meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(title)}</title>'
        f'<meta name="description" content="{esc(description)}">'
        f'<link rel="canonical" href="{esc(canonical)}">'
        f'<meta name="robots" content="index, follow">'
        f'<meta property="og:type" content="website">'
        f'<meta property="og:site_name" content="{esc(site["name"])}">'
        f'<meta property="og:title" content="{esc(title)}">'
        f'<meta property="og:description" content="{esc(description)}">'
        f'<meta property="og:url" content="{esc(canonical)}">'
        f'{og_img}'
        f'<meta name="twitter:card" content="{tw}">'
        f'{theme.font_link(site)}'
        f'<style>{theme.stylesheet(site)}</style>'
        f'{ga}{extra}'
        f'</head><body>')


def nav(site, *, home=False):
    w = words(site)
    brand = esc(site["name"])
    title = brand if home else f'<a href="/">{brand}</a>'
    links = "".join(
        f'<a href="{esc(l["url"])}" target="_blank" rel="noopener">{esc(l["label"])}</a>'
        for l in site.get("links") or [])
    if not home:
        links = f'<a href="/">{esc(w["works"])}</a>' + links
    return (f'<header class="pfnav"><div><h1 class="brand">{title}</h1>'
            f'<p class="tagline">{esc(site["tagline"])}</p></div>'
            f'<nav class="navlinks">{links}</nav></header>')


def footer(site):
    w = words(site)
    items = "".join(
        f'<li><a class="{"primary" if c.get("primary") else ""}" '
        f'href="{esc(c["url"])}" target="_blank" rel="noopener">{esc(c["label"])}</a></li>'
        for c in site["contacts"])
    facts = ""
    if site.get("facts"):
        facts = ('<ul class="facts">'
                 + "".join(f"<li>{esc(f)}</li>" for f in site["facts"]) + "</ul>")
    return (f'<footer class="foot"><div class="pf">'
            f'<h2>{esc(w["contact"])}</h2>'
            f'<ul class="cts">{items}</ul>{facts}'
            f'<p class="small">{esc(site["name"])} · {date.today().year}</p>'
            f'</div></footer>')


def player_and_modal(site):
    return (
        '<div id="player" aria-live="polite"><div class="inner">'
        '<iframe id="pframe" title="Плеер Spotify" allow="autoplay; encrypted-media" '
        'loading="lazy" src="about:blank"></iframe></div></div>'
        '<div id="amodal" role="dialog" aria-modal="true" aria-labelledby="atitle">'
        '<div class="box"><button class="close" aria-label="Закрыть">&times;</button>'
        '<header><img id="acover" alt="" src="" width="64" height="64">'
        '<div><p class="who" id="awho"></p><h2 id="atitle"></h2></div></header>'
        '<ol id="alist"></ol></div></div>')


# ── главная ─────────────────────────────────────────────────────────

def _tile(site, rel, album_index=None):
    cover = f'/covers/{esc(rel["cover"])}.jpg'
    artist = esc(rel["artist"])
    title = esc(rel["title"])
    genre = esc(rel.get("genre") or "")
    if rel["type"] == "album":
        n = len(rel.get("tracks", []))
        w = words(site)["tracks_word"]
        badge = f'<span class="tbadge">{n} {plural(n, w)}</span>'
        action = f'onclick="openAlbum({album_index})"'
        cls = "tile album"
    else:
        badge = ""
        action = f"onclick=\"play(this)\" data-id=\"{esc(rel['id'])}\""
        cls = "tile"
    return (f'<li><button type="button" class="{cls}" data-g="{genre}" {action}>'
            f'<img src="{cover}" alt="{artist} — {title}" loading="lazy" '
            f'width="640" height="640">{badge}'
            f'<span class="tmeta"><span class="tartist">{artist}</span>'
            f'<span class="ttitle">{title}</span></span></button></li>')


def _filters(site, releases):
    if not site.get("genres"):
        return ""
    codes = ["ALL"] + list(site["genres"])
    out = []
    for code in codes:
        n = len(releases) if code == "ALL" else sum(
            1 for r in releases if r.get("genre") == code)
        if n == 0 and code != "ALL":
            continue
        pressed = "true" if code == "ALL" else "false"
        out.append(f'<button type="button" data-f="{esc(code)}" '
                   f'aria-pressed="{pressed}">{esc(genre_label(site, code))}'
                   f'<span class="fc">{n}</span></button>')
    return f'<div class="filters">{"".join(out)}</div>'


def render_index(site, data):
    releases = order_releases(site, data["releases"])
    albums, tiles = [], []
    for rel in releases:
        if rel["type"] == "album":
            tiles.append(_tile(site, rel, len(albums)))
            albums.append({
                "artist": rel["artist"], "title": rel["title"],
                "cover": rel["cover"],
                "tracks": [{"id": t["id"], "title": t["title"]}
                           for t in rel.get("tracks", [])]})
        else:
            tiles.append(_tile(site, rel))
    desc = site.get("description") or f'{site["name"]} — {site["tagline"]}'
    title = f'{site["name"]} — {site["tagline"]}'
    app_js = (TEMPLATES / "app.js").read_text(encoding="utf-8")
    body = (
        f'{head(site, title=title, description=desc, canonical=f"{site['url']}/")}'
        f'<div class="pf">{nav(site, home=True)}'
        f'{_filters(site, releases)}'
        f'<ul class="grid">{"".join(tiles)}</ul></div>'
        f'{footer(site)}{player_and_modal(site)}'
        f'<script>const ALBUMS={json.dumps(albums, ensure_ascii=False)};</script>'
        f'<script src="https://open.spotify.com/embed/iframe-api/v1" async></script>'
        f'<script>{app_js}</script></body></html>')
    return body


# ── страницы треков ─────────────────────────────────────────────────

def track_entries(site, data):
    entries = []
    for rel in order_releases(site, data["releases"]):
        if rel["type"] == "album":
            for tr in rel.get("tracks", []):
                entries.append({
                    "id": tr["id"], "title": tr["title"],
                    "artist": tr.get("artist") or rel["artist"],
                    "year": rel.get("year"), "cover": rel["cover"],
                    "roles": tr.get("roles") or rel.get("roles") or ["mix"],
                    "album": rel["title"]})
        else:
            entries.append({
                "id": rel["id"], "title": rel["title"], "artist": rel["artist"],
                "year": rel.get("year"), "cover": rel["cover"],
                "roles": rel.get("roles") or ["mix"], "album": None,
                "feat": rel.get("feat") or []})
    used = {}
    for entry in entries:
        base = slugify(entry["artist"], entry["title"]) or slugify(entry["id"])
        slug = base
        if base in used:
            slug = slugify(base, entry.get("year") or "")
            if slug in used:
                slug = f"{base}-{used[base] + 1}"
        used[base] = used.get(base, 0) + 1
        used[slug] = used.get(slug, 0)
        entry["slug"] = slug
    return entries


def render_track_page(site, entry):
    role = primary_role(site, entry["roles"])
    verb = site["roles"].get(role, {}).get("verb", "Кто работал над")
    role_words = [site["roles"][r]["word"] for r in config.ROLE_ORDER
                  if r in entry["roles"] and r in site["roles"]]
    title_line = f'{verb} «{entry["title"]}» — {entry["artist"]}'
    canonical = f'{site["url"]}/track/{entry["slug"]}/'
    cover = f'/covers/{entry["cover"]}.jpg'
    who = ", ".join(role_words).lower()
    lead = (f'«{entry["title"]}» — {entry["artist"]}'
            + (f', {entry["year"]} год' if entry.get("year") else "")
            + f'. {who.capitalize()}: {site["name"]}.')
    if entry.get("album"):
        lead += f' Из альбома «{entry["album"]}».'
    jsonld = {
        "@context": "https://schema.org",
        "@type": "MusicRecording",
        "name": entry["title"],
        "byArtist": {"@type": "MusicGroup", "name": entry["artist"]},
        "url": canonical,
        "image": f'{site["url"]}{cover}',
        "contributor": {
            "@type": "Person", "name": site["name"], "url": f'{site["url"]}/',
            "jobTitle": ", ".join(role_words)},
    }
    if entry.get("year"):
        jsonld["datePublished"] = str(entry["year"])
    w = words(site)
    roles_html = "".join(f"<li>{esc(word)}</li>" for word in role_words)
    return (
        f'{head(site, title=f"{title_line} · {site["name"]}", description=lead, canonical=canonical, image=cover)}'
        f'<div class="pf">{nav(site)}'
        f'<a class="back" href="/">{esc(w["back"])}</a>'
        f'<article class="trk">'
        f'<img class="cover" src="{cover}" alt="{esc(entry["artist"])} — {esc(entry["title"])}" '
        f'width="640" height="640">'
        f'<div><h1>{esc(title_line)}</h1>'
        f'<p class="lead">{esc(lead)}</p>'
        f'<ul class="roles">{roles_html}</ul>'
        f'<iframe class="embed" title="{esc(entry["title"])} — Spotify" loading="lazy" '
        f'src="https://open.spotify.com/embed/track/{esc(entry["id"])}?theme=0" '
        f'allow="encrypted-media"></iframe>'
        f'<p><a class="back" href="/track/">{esc(w["all_tracks"])} →</a></p>'
        f'</div></article></div>'
        f'{footer(site)}'
        f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>'
        f'</body></html>')


def render_hub(site, entries):
    w = words(site)
    by_artist = {}
    for entry in entries:
        by_artist.setdefault(entry["artist"], []).append(entry)
    blocks = []
    for artist, items in by_artist.items():
        links = "".join(
            f'<li><a href="/track/{esc(e["slug"])}/">{esc(e["title"])}'
            + (f'<span class="yr">{esc(e["year"])}</span>' if e.get("year") else "")
            + "</a></li>" for e in items)
        blocks.append(f'<section><h2>{esc(artist)}</h2><ul>{links}</ul></section>')
    desc = f'{site["name"]} — {w["hub_title"].lower()}: {len(entries)}.'
    return (
        f'{head(site, title=f"{w["hub_title"]} · {site["name"]}", description=desc, canonical=f"{site['url']}/track/")}'
        f'<div class="pf hub">{nav(site)}'
        f'<h1>{esc(w["hub_title"])} <span class="yr">{len(entries)}</span></h1>'
        f'{"".join(blocks)}</div>{footer(site)}</body></html>')


def render_sitemap(site, entries):
    today = date.today().isoformat()
    urls = [f'{site["url"]}/', f'{site["url"]}/track/']
    urls += [f'{site["url"]}/track/{e["slug"]}/' for e in entries]
    body = "".join(
        f"<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{body}</urlset>")


def render_robots(site):
    return f"User-agent: *\nAllow: /\n\nSitemap: {site['url']}/sitemap.xml\n"


def render_site(site, data, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = track_entries(site, data)
    (out / "index.html").write_text(render_index(site, data), encoding="utf-8")
    track_dir = out / "track"
    track_dir.mkdir(exist_ok=True)
    (track_dir / "index.html").write_text(render_hub(site, entries), encoding="utf-8")
    for entry in entries:
        page_dir = track_dir / entry["slug"]
        page_dir.mkdir(exist_ok=True)
        (page_dir / "index.html").write_text(
            render_track_page(site, entry), encoding="utf-8")
    (out / "sitemap.xml").write_text(render_sitemap(site, entries), encoding="utf-8")
    (out / "robots.txt").write_text(render_robots(site), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return {"tracks": len(entries),
            "releases": len([r for r in data["releases"] if not r.get("hidden")])}
