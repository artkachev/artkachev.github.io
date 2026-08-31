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
           "tracks_word": ("трек", "трека", "треков"),
           "artists_word": ("артист", "артиста", "артистов"),
           "albums_word": ("альбом", "альбома", "альбомов"),
           "album_word": "Альбом", "singles_word": "Синглы",
           "by_letter": "По алфавиту", "faq": "Вопросы", "pause": "Пауза",
           "genre_word": "Жанр", "role_word": "Роль", "all_word": "Все",
           "multi_hint": "можно несколько", "about_track": "О треке",
           "search_hint": "Поиск по артисту, альбому или треку",
           "clear": "Очистить", "no_hits": "Ничего не нашлось. Попробуйте короче или по-другому.",
           "nothing": "Работ сразу со всеми этими ролями нет. Снимите один фильтр.",
           "catalog_lead": "Полный каталог работ",
           "among_them": "среди них",
           "catalog_hint": "Ищите по артисту, альбому или названию трека."},
    "en": {"works": "Works", "all_tracks": "All tracks", "back": "← All works",
           "listen": "Listen", "contact": "Get in touch", "hub_title": "All tracks",
           "tracks_word": ("track", "tracks", "tracks"),
           "artists_word": ("artist", "artists", "artists"),
           "albums_word": ("album", "albums", "albums"),
           "album_word": "Album", "singles_word": "Singles",
           "by_letter": "By letter", "faq": "FAQ", "pause": "Pause",
           "genre_word": "Genre", "role_word": "Role", "all_word": "All",
           "multi_hint": "combine", "about_track": "About",
           "search_hint": "Search by artist, album or track",
           "clear": "Clear", "no_hits": "Nothing found. Try a shorter query.",
           "nothing": "Nothing matches all of these. Remove one filter.",
           "catalog_lead": "Full catalogue of works",
           "among_them": "among them",
           "catalog_hint": "Search by artist, album or track title."},
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
    # размеры знаем только у общей картинки сайта; у страницы трека
    # превью — квадратная обложка, и подписывать ей 1200×630 нельзя
    size = [] if image else (site.get("og_image_size") or [])
    if img_abs and len(size) == 2:
        og_img += (f'<meta property="og:image:width" content="{int(size[0])}">'
                   f'<meta property="og:image:height" content="{int(size[1])}">')
    tw = "summary_large_image" if img_abs else "summary"
    icons = site.get("icons") or {}
    ico = ""
    if icons.get("svg"):
        ico += f'<link rel="icon" href="{esc(icons["svg"])}" type="image/svg+xml">'
    if icons.get("png"):
        ico += f'<link rel="icon" href="{esc(icons["png"])}" sizes="32x32" type="image/png">'
    if icons.get("apple"):
        ico += f'<link rel="apple-touch-icon" href="{esc(icons["apple"])}">'
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
        f'{ico}'
        f'{theme.font_link(site)}'
        f'<style>{theme.stylesheet(site)}</style>'
        f'{ga}{extra}'
        f'</head><body>')


def load_logo_svg(site, project):
    """Содержимое логотипа, если это svg рядом с проектом.

    Встраиваем его в страницу, а не подключаем через <img>: картинка в теге
    img — отдельный документ, внутри неё currentColor не видит страницу и
    падает в чёрный. Встроенный svg красится обычным CSS.
    """
    logo = site.get("logo") or ""
    if not logo.endswith(".svg") or logo.startswith("http"):
        return None
    path = Path(project) / logo.lstrip("/")
    if not path.exists():
        return None
    svg = path.read_text(encoding="utf-8").strip()
    return svg if svg.startswith("<svg") else None


def brand_mark(site):
    """Знак плюс имя. Без логотипа — просто имя, набранное шрифтом.

    Когда logo_wordmark выключен, знак остаётся один, а имя уходит в подпись:
    без него шапка теряет и текст для поиска, и озвучку для читалок с экрана.
    """
    name = esc(site["name"])
    logo = site.get("logo")
    if not logo:
        return name
    with_word = site.get("logo_wordmark", True)
    svg = site.get("logo_svg")
    if svg:
        label = ("aria-hidden=\"true\"" if with_word
                 else f'role="img" aria-label="{name}"')
        mark = svg.replace("<svg", f'<svg class="logomark" focusable="false" '
                                   f'{label}', 1)
    else:
        mark = f'<img class="logomark" src="{esc(logo)}" '\
               f'alt="{"" if with_word else name}">'
    if not with_word:
        return mark
    return f'<span class="lockup">{mark}<span>{name}</span></span>'


def nav(site, *, home=False):
    w = words(site)
    brand = brand_mark(site)
    title = brand if home else f'<a href="/">{brand}</a>'
    links = "".join(
        f'<a href="{esc(l["url"])}" target="_blank" rel="noopener">{esc(l["label"])}</a>'
        for l in site.get("links") or [])
    inner = f'<a href="/track/">{esc(w["hub_title"])}</a>'
    if site.get("has_faq"):
        inner += f'<a href="/faq/">{esc(w["faq"])}</a>'
    if not home:
        inner = f'<a href="/">{esc(w["works"])}</a>' + inner
    links = inner + links
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

PLAY_ICON = ('<svg class="ico play" viewBox="0 0 24 24" aria-hidden="true">'
             '<path d="M8 5.2v13.6L19 12z"/></svg>')
PAUSE_ICON = ('<svg class="ico pause" viewBox="0 0 24 24" aria-hidden="true">'
              '<path d="M6.5 5h3.6v14H6.5zM13.9 5h3.6v14h-3.6z"/></svg>')


def _tile(site, rel, album_index=None, slug=None):
    """Плитка работы.

    Кнопки лежат соседями плитки, а не внутри неё: кнопка и ссылка внутри
    кнопки — невалидная разметка, и с клавиатуры до них не добраться.
    """
    w = words(site)
    cover = f'/covers/{esc(rel["cover"])}.jpg'
    artist = esc(rel["artist"])
    title = esc(rel["title"])
    genre = esc(rel.get("genre") or "")
    roles = " ".join(release_roles(rel))
    if rel["type"] == "album":
        n = len(rel.get("tracks", []))
        badge = f'<span class="tbadge">{n} {plural(n, w["tracks_word"])}</span>'
        attrs = f'data-album="{album_index}"'
        cls, acts = "tile album", ""
    else:
        badge = ""
        attrs = f'data-id="{esc(rel["id"])}"'
        cls = "tile"
        play = (f'<button type="button" class="pbtn" '
                f'data-label="{artist} — {title}" '
                f'aria-label="{esc(w["listen"])}: {artist} — {title}">'
                f'{PLAY_ICON}{PAUSE_ICON}</button>')
        # настоящая ссылка, а не кнопка: открывается в новой вкладке
        # и даёт с главной прямые ссылки на страницы треков
        info = ""
        if slug:
            info = (f'<a class="ibtn" href="/track/{esc(slug)}/" '
                    f'aria-label="{esc(w["about_track"])}: {artist} — {title}">'
                    f'{esc(w["about_track"])}</a>')
        acts = f'<div class="acts">{play}{info}</div>'
    return (f'<li class="cell"><button type="button" class="{cls}" '
            f'data-g="{genre}" data-r="{esc(roles)}" {attrs}>'
            f'<img src="{cover}" alt="{artist} — {title}" loading="lazy" '
            f'width="640" height="640">{badge}'
            f'<span class="tmeta"><span class="tartist">{artist}</span>'
            f'<span class="ttitle">{title}</span></span></button>{acts}</li>')


def release_roles(rel):
    """Роли релиза. У альбома — объединение ролей его треков."""
    if rel["type"] != "album":
        return [k for k in config.ROLE_ORDER if k in (rel.get("roles") or [])]
    found = set()
    for tr in rel.get("tracks", []):
        found |= set(tr.get("roles") or [])
    if not found:
        found = set(rel.get("roles") or [])
    return [k for k in config.ROLE_ORDER if k in found]


def _filter_row(site, releases, *, dim, label, codes, name_of, match, multi=False):
    """Одна строка фильтров: «Все» плюс те значения, которые реально есть.

    Числа у кнопок — сколько работ останется, если включить этот фильтр.
    Дальше их пересчитывает app.js, потому что после первого выбора
    исходные числа перестают быть правдой.
    """
    out = []
    for code in ["ALL"] + list(codes):
        n = len(releases) if code == "ALL" else sum(
            1 for r in releases if match(r, code))
        if n == 0 and code != "ALL":
            continue
        pressed = "true" if code == "ALL" else "false"
        out.append(f'<button type="button" data-f="{esc(code)}" '
                   f'aria-pressed="{pressed}">{esc(name_of(code))}'
                   f'<span class="fc">{n}</span></button>')
    if len(out) < 3:                      # «Все» плюс один вариант — не фильтр
        return ""
    hint = ""
    flag = ""
    if multi:
        hint = f' <span class="fhint">{esc(words(site)["multi_hint"])}</span>'
        flag = ' data-multi="1"'
    return (f'<div class="filters" data-dim="{esc(dim)}"{flag} '
            f'role="group" aria-label="{esc(label)}">'
            f'<span class="flabel">{esc(label)}{hint}</span>{"".join(out)}</div>')


def _filters(site, releases):
    w = words(site)
    rows = []
    if site.get("genres"):
        rows.append(_filter_row(
            site, releases, dim="g", label=w["genre_word"],
            codes=site["genres"],
            name_of=lambda c: w["all_word"] if c == "ALL" else genre_label(site, c),
            match=lambda r, c: r.get("genre") == c))
    roles = [k for k in config.ROLE_ORDER if k in (site.get("roles") or {})]
    rows.append(_filter_row(
        site, releases, dim="r", label=w["role_word"], codes=roles,
        name_of=lambda c: (w["all_word"] if c == "ALL"
                           else site["roles"][c]["word"]),
        match=lambda r, c: c in release_roles(r), multi=True))
    rows = [r for r in rows if r]
    return f'<div class="filterbar">{"".join(rows)}</div>' if rows else ""


def render_index(site, data, entries):
    releases = order_releases(site, data["releases"])
    slug_of = {e["id"]: e["slug"] for e in entries}
    albums, tiles = [], []
    for rel in releases:
        if rel["type"] == "album":
            tiles.append(_tile(site, rel, len(albums)))
            albums.append({
                "artist": rel["artist"], "title": rel["title"],
                "cover": rel["cover"],
                "tracks": [{"id": t["id"], "title": t["title"],
                            "slug": slug_of.get(t["id"])}
                           for t in rel.get("tracks", [])]})
        else:
            tiles.append(_tile(site, rel, slug=slug_of.get(rel["id"])))
    desc = site.get("description") or f'{site["name"]} — {site["tagline"]}'
    title = f'{site["name"]} — {site["tagline"]}'
    app_js = (TEMPLATES / "app.js").read_text(encoding="utf-8")
    canonical = f"{site['url']}/"
    body = (
        f'{head(site, title=title, description=desc, canonical=canonical)}'
        f'<div class="pf">{nav(site, home=True)}'
        f'{_filters(site, releases)}'
        f'<ul class="grid" data-listen="{esc(words(site)["listen"])}" data-pause="{esc(words(site)["pause"])}" data-about="{esc(words(site)["about_track"])}">{"".join(tiles)}</ul>'
        f'<p class="nothing" hidden>{esc(words(site)["nothing"])}</p></div>'
        f'{footer(site)}{player_and_modal(site)}'
        # именно var: const на верхнем уровне не попадает в window,
        # а app.js читает список как window.ALBUMS
        f'<script>var ALBUMS={json.dumps(albums, ensure_ascii=False)};</script>'
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
                "roles": rel.get("roles") or ["mix"],
                "album": rel.get("album"),
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
    page_title = f'{title_line} · {site["name"]}'
    return (
        f'{head(site, title=page_title, description=lead, canonical=canonical, image=cover)}'
        f'<div class="pf">{nav(site)}'
        f'<a class="back" href="/">{esc(w["back"])}</a>'
        f'<article class="trk">'
        f'<div class="coverbox">'
        f'<img class="cover" src="{cover}" alt="{esc(entry["artist"])} — {esc(entry["title"])}" '
        f'width="640" height="640"></div>'
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


def main_artist(name):
    """Первый исполнитель: «VERBEE, Анетта» → «VERBEE»."""
    return (name or "").split(",")[0].strip()


def guests(full, primary):
    """Остальные исполнители трека, кроме основного."""
    return [a.strip() for a in (full or "").split(",")[1:]
            if a.strip() and a.strip() != primary]


def letter_of(name):
    """Буква для указателя. Возвращает (группа, буква): латиница, кириллица, прочее."""
    ch = (name or "#")[:1].upper()
    if "A" <= ch <= "Z":
        return (0, ch)
    if "А" <= ch <= "Я" or ch == "Ё":
        return (1, "Е" if ch == "Ё" else ch)
    return (2, "#")


def catalog(site, data, entries):
    """Артисты по алфавиту, у каждого — альбомы и отдельно синглы."""
    slug_of = {e["id"]: e["slug"] for e in entries}
    shelf = {}
    for rel in order_releases(site, data["releases"]):
        primary = main_artist(rel["artist"])
        who = shelf.setdefault(primary, {"albums": [], "singles": [], "count": 0})
        if rel["type"] == "album":
            tracks = [t for t in rel.get("tracks", []) if t["id"] in slug_of]
            if not tracks:
                continue
            who["albums"].append({
                "title": rel["title"], "year": rel.get("year"),
                "tracks": [{"title": t["title"], "slug": slug_of[t["id"]],
                            "guests": guests(t.get("artist") or rel["artist"], primary)}
                           for t in tracks]})
            who["count"] += len(tracks)
        elif rel["id"] in slug_of:
            who["singles"].append({
                "title": rel["title"], "year": rel.get("year"),
                "slug": slug_of[rel["id"]],
                "guests": guests(rel["artist"], primary)})
            who["count"] += 1
    return dict(sorted(shelf.items(), key=lambda kv: (letter_of(kv[0]), kv[0].upper())))


def _guest_note(names):
    return f' <span class="with">· с {esc(", ".join(names))}</span>' if names else ""


def search_key(*parts):
    """Строка для поиска: сам текст плюс его латиница.

    Каталог подписан как в Spotify — «Klava Koka», — а искать будут и
    «клава». Держим обе записи рядом, тогда совпадёт любая.
    """
    text = " ".join(str(p) for p in parts if p).lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text).strip()
    lat = "".join(TRANSLIT.get(ch, ch) for ch in text)
    return text if lat == text else f"{text} {lat}"


def _track_li(item, *, show_year, artist, album=None):
    year = (f'<span class="yr">{esc(item["year"])}</span>'
            if show_year and item.get("year") else "")
    key = search_key(item["title"], " ".join(item["guests"]), artist, album)
    return (f'<li data-s="{esc(key)}">'
            f'<a href="/track/{esc(item["slug"])}/">{esc(item["title"])}'
            f'{_guest_note(item["guests"])}{year}</a></li>')


def render_hub(site, data, entries):
    w = words(site)
    shelf = catalog(site, data, entries)

    letters, blocks = [], []
    seen_letter = None
    for artist, who in shelf.items():
        group, ch = letter_of(artist)
        if ch != seen_letter:
            seen_letter = ch
            letters.append(ch)
            blocks.append(f'<h2 class="ltr" id="l-{esc(slugify(ch) or "n")}">'
                          f'{esc(ch)}</h2>')
        parts = []
        for album in who["albums"]:
            year = (f'<span class="yr">{esc(album["year"])}</span>'
                    if album.get("year") else "")
            rows = "".join(_track_li(t, show_year=False, artist=artist,
                                     album=album["title"])
                           for t in album["tracks"])
            parts.append(
                f'<div class="alb" data-s="{esc(search_key(album["title"], artist))}">'
                f'<p class="albhead">«{esc(album["title"])}»'
                f'{year} <span class="albtag">{esc(w["album_word"])}</span></p>'
                f'<ul>{rows}</ul></div>')
        if who["singles"]:
            head_line = (f'<p class="subhead">{esc(w["singles_word"])}</p>'
                         if who["albums"] else "")
            rows = "".join(_track_li(s, show_year=True, artist=artist)
                           for s in who["singles"])
            parts.append(f'<div class="sing">{head_line}<ul>{rows}</ul></div>')
        n = who["count"]
        blocks.append(
            f'<section class="art" id="a-{esc(slugify(artist))}" '
            f'data-s="{esc(search_key(artist))}">'
            f'<h3>{esc(artist)}<span class="cnt">{n}</span></h3>'
            f'{"".join(parts)}</section>')

    nav_letters = "".join(
        f'<a href="#l-{esc(slugify(ch) or "n")}">{esc(ch)}</a>' for ch in letters)

    n_tracks, n_artists = len(entries), len(shelf)
    n_albums = sum(len(v["albums"]) for v in shelf.values())
    top = [a for a, _ in sorted(shelf.items(), key=lambda kv: -kv[1]["count"])[:6]]
    tw, aw = w["tracks_word"], w["artists_word"]
    counter = (f'{n_tracks} {plural(n_tracks, tw)} · {n_artists} {plural(n_artists, aw)}'
               + (f' · {n_albums} {plural(n_albums, w["albums_word"])}' if n_albums else ""))
    scope = (f'{n_tracks} {plural(n_tracks, tw)} для '
             f'{n_artists} {plural(n_artists, aw)}')
    lead = (f'{esc(site["name"])} — {esc(site["tagline"])}. '
            f'{esc(w["catalog_lead"])}: {esc(scope)}, '
            f'{esc(w["among_them"])} {esc(", ".join(top))}. '
            f'{esc(w["catalog_hint"])}')

    desc = (f'{w["hub_title"]} — {site["name"]}, {site["tagline"]}. '
            f'{w["catalog_lead"]}: {scope}. {w["catalog_hint"]}')[:300]
    page_title = f'{w["hub_title"]} — {site["name"]}'
    canonical = f"{site['url']}/track/"
    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": page_title,
        "url": canonical,
        "description": desc,
        "inLanguage": site["lang"],
        "about": {"@type": "Person", "name": site["name"], "url": f'{site["url"]}/'},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": n_tracks,
            "itemListElement": [
                {"@type": "ListItem", "position": i,
                 "url": f'{site["url"]}/track/{e["slug"]}/',
                 "name": f'{e["artist"]} — {e["title"]}'}
                for i, e in enumerate(entries, 1)],
        },
    }
    return (
        f'{head(site, title=page_title, description=desc, canonical=canonical)}'
        f'<div class="pf hub">{nav(site)}'
        f'<a class="back" href="/">{esc(w["back"])}</a>'
        f'<h1>{esc(w["hub_title"])}</h1>'
        f'<p class="lead">{lead}</p>'
                f'<div class="search">'
        f'<input type="search" id="q" autocomplete="off" '
        f'placeholder="{esc(w["search_hint"])}" aria-label="{esc(w["search_hint"])}">'
        f'<button type="button" id="qclear" hidden '
        f'aria-label="{esc(w["clear"])}">&times;</button></div>'
        f'<p class="counter" id="counter" data-tpl="{esc(counter)}" '
        f'data-tw="{esc("|".join(tw))}" data-aw="{esc("|".join(aw))}">'
        f'{esc(counter)}</p>'
        f'<nav class="alpha" aria-label="{esc(w["by_letter"])}">{nav_letters}</nav>'
        f'{"".join(blocks)}'
        f'<p class="nothing" id="nohits" hidden>{esc(w["no_hits"])}</p></div>'
        f'{footer(site)}'
        f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>'
        f'<script>{(TEMPLATES / "hub.js").read_text(encoding="utf-8")}</script>'
        f'</body></html>')


def esc_join(names):
    return esc(", ".join(names))


# ── вопросы и ответы ────────────────────────────────────────────────

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def inline(text):
    """Мини-разметка ответов: [текст](ссылка) и **выделение**.

    Сначала экранируем всё целиком, потом размечаем — поэтому в faq.json
    нельзя случайно занести сырой HTML.
    """
    out = esc(text)
    out = LINK_RE.sub(
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', out)
    return BOLD_RE.sub(lambda m: f'<span class="num">{m.group(1)}</span>', out)


def plain(text):
    """Тот же текст без разметки — для schema.org и описания страницы."""
    out = LINK_RE.sub(lambda m: m.group(1), str(text or ""))
    return BOLD_RE.sub(lambda m: m.group(1), out)


def render_faq(site, faq):
    sections = faq.get("sections") or []
    items = [(s, it) for s in sections for it in s.get("items") or []]

    tabs = "".join(
        f'<a href="#s-{esc(s["id"])}">{esc(s["title"])}'
        f'<span class="fc">{len(s.get("items") or [])}</span></a>'
        for s in sections)

    blocks = []
    for section in sections:
        rows = "".join(
            f'<details id="q-{esc(slugify(it["q"]))}">'
            f'<summary>{esc(it["q"])}</summary>'
            f'<div class="ans">{inline(it["a"])}</div></details>'
            for it in section.get("items") or [])
        blocks.append(
            f'<section class="faqsec" id="s-{esc(section["id"])}">'
            f'<h2>{esc(section["title"])}</h2>{rows}</section>')

    canonical = f"{site['url']}/faq/"
    title = faq.get("title") or f'{site["name"]} — вопросы и ответы'
    desc = plain(faq.get("summary") or "")[:300]
    jsonld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "url": canonical,
        "name": title,
        "inLanguage": site["lang"],
        "about": {"@type": "Person", "name": site["name"],
                  "url": f'{site["url"]}/', "jobTitle": site["tagline"]},
        "mainEntity": [
            {"@type": "Question", "name": plain(it["q"]),
             "acceptedAnswer": {"@type": "Answer", "text": plain(it["a"])}}
            for _, it in items],
    }
    if faq.get("updated"):
        jsonld["dateModified"] = faq["updated"]

    updated = ""
    if faq.get("updated"):
        updated = (f'<p class="small upd">Последнее обновление: '
                   f'{esc(faq["updated"])}.</p>')
    summary = ""
    if faq.get("summary"):
        summary = (f'<aside class="tldr">'
                   f'<p class="subhead">{esc(faq.get("summary_label") or "Коротко")}</p>'
                   f'<p>{inline(faq["summary"])}</p></aside>')

    return (
        f'{head(site, title=title, description=desc, canonical=canonical)}'
        f'<div class="pf faq">{nav(site)}'
        f'<a class="back" href="/track/">← {esc(words(site)["hub_title"])}</a>'
        f'<h1>{esc(faq.get("heading") or "Вопросы и ответы")}</h1>'
        + (f'<p class="lead">{inline(faq["intro"])}</p>' if faq.get("intro") else "")
        + f'{summary}'
        f'<nav class="faqtabs" aria-label="Разделы">{tabs}</nav>'
        f'{"".join(blocks)}{updated}</div>'
        f'{footer(site)}'
        f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>'
        f'</body></html>')


def render_sitemap(site, entries, extra=()):
    today = date.today().isoformat()
    urls = [f'{site["url"]}/', f'{site["url"]}/track/']
    urls += list(extra)
    urls += [f'{site["url"]}/track/{e["slug"]}/' for e in entries]
    body = "".join(
        f"<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{body}</urlset>")


def render_robots(site):
    return f"User-agent: *\nAllow: /\n\nSitemap: {site['url']}/sitemap.xml\n"


def render_site(site, data, out_dir, faq=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    site = dict(site, has_faq=bool(faq),
                logo_svg=load_logo_svg(site, out_dir))
    entries = track_entries(site, data)
    (out / "index.html").write_text(
        render_index(site, data, entries), encoding="utf-8")
    track_dir = out / "track"
    track_dir.mkdir(exist_ok=True)
    (track_dir / "index.html").write_text(
        render_hub(site, data, entries), encoding="utf-8")
    for entry in entries:
        page_dir = track_dir / entry["slug"]
        page_dir.mkdir(exist_ok=True)
        (page_dir / "index.html").write_text(
            render_track_page(site, entry), encoding="utf-8")
    extra = []
    if faq:
        faq_dir = out / "faq"
        faq_dir.mkdir(exist_ok=True)
        (faq_dir / "index.html").write_text(render_faq(site, faq), encoding="utf-8")
        extra.append(f'{site["url"]}/faq/')
    (out / "sitemap.xml").write_text(
        render_sitemap(site, entries, extra), encoding="utf-8")
    (out / "robots.txt").write_text(render_robots(site), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return {"tracks": len(entries),
            "releases": len([r for r in data["releases"] if not r.get("hidden")]),
            "faq": sum(len(s.get("items") or []) for s in (faq or {}).get("sections") or [])}
