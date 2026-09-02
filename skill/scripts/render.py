"""Сборка всех страниц сайта из site.json и data.json.

Готовый HTML здесь только пишется и никогда не разбирается обратно —
источник истины всегда данные, а не вёрстка.
"""
import hashlib
import html
import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import checks
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

LOCALE = {"ru": "ru_RU", "en": "en_US"}

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
           "catalog_lead": "Каталог работ",
           "among_them": "среди них",
           "catalog_hint": "Ищите по артисту, альбому или названию трека.",
           "crumbs": "Хлебные крошки", "about": "О себе",
           "worked_with": "С кем работал", "elsewhere": "Где ещё"},
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
           "catalog_lead": "Catalogue of works",
           "among_them": "among them",
           "catalog_hint": "Search by artist, album or track title.",
           "crumbs": "Breadcrumb", "about": "About",
           "worked_with": "Worked with", "elsewhere": "Elsewhere"},
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


def credit_name(site):
    """Как подписывать авторство: «КАССА (Артем Ткачев)».

    Настоящее имя берётся из site.json → real_name. Без него остаётся
    только рабочее имя, и строка не ломается.
    """
    if site.get("real_name"):
        return f'{site["name"]} ({site["real_name"]})'
    return site["name"]


def primary_role(site, roles):
    """Главная роль — первая по важности из объявленных в настройках."""
    for key in config.ROLE_ORDER:
        if key in (roles or []) and key in site["roles"]:
            return key
    return (roles or ["mix"])[0]


def order_releases(site, releases, *, include_hidden=False):
    """Работы в порядке показа. Скрытые — только там, где их ждут.

    «Спрятать» означает «убрать с витрины», а не «убрать с сайта»: страница
    работы остаётся, попадает в каталог, в sitemap и в llms.txt и дальше
    приносит людей из поиска. Витрина — единственное место, где скрытая
    работа не показывается, поэтому только render_index зовёт это без флажка.

    Раньше фильтр стоял здесь безусловно, и скрытая работа выпадала из
    track_entries, то есть из всего сразу. Страница при этом оставалась
    лежать в репозитории от прежней сборки — уже никем не обновляемая и без
    единой ссылки на себя: ни в каталоге, ни в карте сайта. Ровно то, чего
    скрытие делать не должно.
    """
    visible = [r for r in releases if include_hidden or not r.get("hidden")]
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

#: что сборщик выдал на каждой странице — для проверок перед публикацией.
#: собирается здесь, а не разбором готового HTML: вёрстка не источник истины
_PAGES = []


def head(site, *, title, description, canonical, image=None, extra=""):
    _PAGES.append({"url": canonical, "title": title, "description": description})
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
    # favicon.ico в корне — первым: Яндекс ищет иконку именно там, и без
    # этого файла в выдаче остаётся серый шарик. Google берёт любой из
    # объявленных, но требует квадрат, кратный 48 пикселям, — 32 ему мало
    if icons.get("ico"):
        ico += f'<link rel="icon" href="{esc(icons["ico"])}" sizes="48x48">'
    if icons.get("svg"):
        ico += f'<link rel="icon" href="{esc(icons["svg"])}" type="image/svg+xml">'
    if icons.get("png"):
        size = int(icons.get("png_size") or 32)
        ico += (f'<link rel="icon" href="{esc(icons["png"])}" '
                f'sizes="{size}x{size}" type="image/png">')
    if icons.get("apple"):
        ico += f'<link rel="apple-touch-icon" href="{esc(icons["apple"])}">'
    # коды подтверждения площадок — Search Console, Вебмастер, Bing.
    # заполняются в site.json → verification, пока пусто — тегов нет
    verify = site.get("verification") or {}
    verify_tags = ""
    if verify.get("google"):
        verify_tags += (f'<meta name="google-site-verification" '
                         f'content="{esc(verify["google"])}">')
    if verify.get("yandex"):
        verify_tags += (f'<meta name="yandex-verification" '
                         f'content="{esc(verify["yandex"])}">')
    if verify.get("bing"):
        verify_tags += (f'<meta name="msvalidate.01" '
                         f'content="{esc(verify["bing"])}">')
    locale = LOCALE.get(site["lang"], site["lang"])
    return (
        f'<!doctype html><html lang="{esc(site["lang"])}"><head>'
        f'<meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(title)}</title>'
        f'<meta name="description" content="{esc(description)}">'
        f'<meta name="author" content="{esc(credit_name(site))}">'
        f'<link rel="canonical" href="{esc(canonical)}">'
        f'<link rel="alternate" type="application/rss+xml" '
        f'title="{esc(site["name"])}" href="/feed.xml">'
        f'<meta name="robots" content="index, follow">'
        f'{verify_tags}'
        f'<meta property="og:type" content="website">'
        f'<meta property="og:site_name" content="{esc(site["name"])}">'
        f'<meta property="og:locale" content="{esc(locale)}">'
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
    # На главной имя — единственный заголовок, ему h1 и положен. На остальных
    # h1 занят темой страницы («Кто спродюсировал…»), и второй h1 с брендом
    # её только размывал.
    tag = "h1" if home else "p"
    links = "".join(
        f'<a href="{esc(l["url"])}" target="_blank" rel="noopener">{esc(l["label"])}</a>'
        for l in site.get("links") or [])
    inner = f'<a href="/track/">{esc(w["hub_title"])}</a>'
    if site.get("has_about"):
        inner += f'<a href="/about/">{esc(w["about"])}</a>'
    if site.get("has_faq"):
        inner += f'<a href="/faq/">{esc(w["faq"])}</a>'
    if not home:
        inner = f'<a href="/">{esc(w["works"])}</a>' + inner
    links = inner + links
    return (f'<header class="pfnav"><div><{tag} class="brand">{title}</{tag}>'
            f'<p class="tagline">{esc(site["tagline"])}</p></div>'
            f'<nav class="navlinks">{links}</nav></header>')


def ld_script(*objs):
    """Блоки JSON-LD подряд. Их может быть несколько на странице —
    поиск читает все, а держать breadcrumbs отдельно от основной сущности
    честнее, чем сшивать разнородное в один объект."""
    return "".join(
        f'<script type="application/ld+json">{json.dumps(o, ensure_ascii=False)}</script>'
        for o in objs if o)


def caps_line(text):
    """Заголовок, набранный прописными: длинное тире поднимаем.

    Тире рисуется по центру строчных, а в капители строчных нет — на фоне
    заглавных оно провисает. Оптически его нужно поднять к середине букв,
    иначе строка выглядит разорванной по низу.
    """
    return '<span class="mdash">—</span>'.join(esc(part) for part in text.split("—"))


def crumbs(site, trail):
    """Хлебные крошки: видимая строка и BreadcrumbList к ней.

    Раньше вверху страницы стояла одна ссылка «назад». Она отвечала, куда
    уйти, но не показывала, где страница лежит, — ни человеку, ни выдаче,
    которая рисует этот путь под ссылкой вместо голого адреса.

    trail — список (название, путь) от корня к текущей странице.
    """
    w = words(site)
    parts = []
    for i, (name, path) in enumerate(trail):
        last = i == len(trail) - 1
        parts.append(f'<span aria-current="page">{esc(name)}</span>' if last
                     else f'<a href="{esc(path)}">{esc(name)}</a>')
    html = (f'<nav class="crumbs" aria-label="{esc(w["crumbs"])}">'
            + '<span class="sep" aria-hidden="true">/</span>'.join(parts)
            + '</nav>')
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList",
          "itemListElement": [
              {"@type": "ListItem", "position": i + 1, "name": name,
               "item": f'{site["url"]}{path}'}
              for i, (name, path) in enumerate(trail)]}
    return html, ld


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
    # приписки внизу: сноска про Meta нужна по российскому закону, раз на
    # сайте есть ссылка на инстаграм. Текст лежит в site.json, а не в коде,
    # чтобы правился без пересборки скриптов
    legal = "".join(f'<p class="small legal">{esc(line)}</p>'
                    for line in site.get("legal") or [])
    return (f'<footer class="foot"><div class="pf">'
            f'<h2>{esc(w["contact"])}</h2>'
            f'<ul class="cts">{items}</ul>{facts}'
            f'<p class="small">{esc(site["name"])} · {date.today().year}</p>'
            f'{legal}</div></footer>')


def player_and_modal(site):
    return (
        '<div id="player" aria-live="polite"><div class="inner">'
        '<iframe id="pframe" title="Плеер Spotify" allow="autoplay; encrypted-media" '
        'loading="lazy" src="about:blank"></iframe></div></div>'
        '<div id="amodal" role="dialog" aria-modal="true" aria-labelledby="atitle">'
        '<div class="box"><button class="close" aria-label="Закрыть">&times;</button>'
        '<header><img id="acover" alt="" width="64" height="64">'
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
    desc = clamp(desc)
    title = f'{site["name"]} — {site["tagline"]}'
    app_js = (TEMPLATES / "app.js").read_text(encoding="utf-8")
    canonical = f"{site['url']}/"
    # Person на главной — чтобы поиск и ИИ-движки знали, кто такой сайт,
    # и связывали рабочее имя с настоящим через alternateName и sameAs
    jsonld = {"@context": "https://schema.org", "@type": "Person",
              # тот же идентификатор стоит у Person на /about/: для поиска это
              # один человек, описанный в двух местах, а не два похожих
              "@id": f'{site["url"]}/#person',
              "name": site["name"], "url": canonical, "jobTitle": site["tagline"],
              "description": desc}
    if site.get("real_name"):
        jsonld["alternateName"] = site["real_name"]
    if site.get("og_image"):
        jsonld["image"] = f'{site["url"]}{site["og_image"]}'
    same_as = [l["url"] for l in all_links(site)]
    if same_as:
        jsonld["sameAs"] = same_as
    email = next((c["url"][7:] for c in site.get("contacts") or []
                  if c.get("url", "").startswith("mailto:")), None)
    if email:
        jsonld["email"] = email
    # WebSite отдельно от Person: он про сайт, а не про человека. Здесь же
    # alternateName — по какому ещё имени этот сайт спрашивают, — и адрес
    # поиска по каталогу, чтобы выдача могла искать прямо у себя
    website = {"@context": "https://schema.org", "@type": "WebSite",
               "name": site["name"], "url": canonical,
               "inLanguage": site["lang"]}
    if site.get("real_name"):
        website["alternateName"] = site["real_name"]
    website["potentialAction"] = {
        "@type": "SearchAction",
        "target": {"@type": "EntryPoint",
                   "urlTemplate": f'{site["url"]}/track/?q={{search_term_string}}'},
        "query-input": "required name=search_term_string"}
    body = (
        f'{head(site, title=title, description=desc, canonical=canonical)}'
        f'<div class="pf">{nav(site, home=True)}'
        f'{_filters(site, releases)}'
        f'<ul class="grid" data-listen="{esc(words(site)["listen"])}" data-pause="{esc(words(site)["pause"])}" data-about="{esc(words(site)["about_track"])}">{"".join(tiles)}</ul>'
        f'<p class="nothing" hidden>{esc(words(site)["nothing"])}</p></div>'
        f'{footer(site)}{player_and_modal(site)}'
        f'{ld_script(jsonld, website)}'
        # именно var: const на верхнем уровне не попадает в window,
        # а app.js читает список как window.ALBUMS
        f'<script>var ALBUMS={json.dumps(albums, ensure_ascii=False)};</script>'
        f'<script src="https://open.spotify.com/embed/iframe-api/v1" async></script>'
        f'<script>{app_js}</script></body></html>')
    return body


# ── страницы треков ─────────────────────────────────────────────────

def track_entries(site, data):
    entries = []
    for rel in order_releases(site, data["releases"], include_hidden=True):
        if rel["type"] == "album":
            for tr in rel.get("tracks", []):
                entries.append({
                    "id": tr["id"], "title": tr["title"],
                    "artist": tr.get("artist") or rel["artist"],
                    "year": rel.get("year"), "cover": rel["cover"],
                    "roles": tr.get("roles") or rel.get("roles") or ["mix"],
                    "about": tr.get("about") or "",
                    "album": rel["title"]})
        else:
            entries.append({
                "id": rel["id"], "title": rel["title"], "artist": rel["artist"],
                "year": rel.get("year"), "cover": rel["cover"],
                "roles": rel.get("roles") or ["mix"],
                "about": rel.get("about") or "",
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


def auto_lead(site, entry):
    """Строка под заголовком, когда своё описание не задано."""
    role_words = [site["roles"][r]["word"] for r in config.ROLE_ORDER
                  if r in entry["roles"] and r in site["roles"]]
    who = ", ".join(role_words).lower()
    lead = (f'«{entry["title"]}» — {entry["artist"]}'
            + (f', {entry["year"]} год' if entry.get("year") else "")
            + f'. {who.capitalize()}: {credit_name(site)}.')
    if entry.get("album"):
        lead += f' Из альбома «{entry["album"]}».'
    return lead


def render_track_page(site, entry):
    role = primary_role(site, entry["roles"])
    verb = site["roles"].get(role, {}).get("verb", "Кто работал над")
    role_words = [site["roles"][r]["word"] for r in config.ROLE_ORDER
                  if r in entry["roles"] and r in site["roles"]]
    title_line = f'{verb} «{entry["title"]}» — {entry["artist"]}'
    canonical = f'{site["url"]}/track/{entry["slug"]}/'
    cover = f'/covers/{entry["cover"]}.jpg'
    lead = (entry.get("about") or "").strip() or auto_lead(site, entry)
    person = {"@type": "Person", "name": site["name"],
              "url": f'{site["url"]}/', "jobTitle": ", ".join(role_words)}
    if site.get("real_name"):
        # рабочее имя и настоящее — один человек, пусть поиск это знает
        person["alternateName"] = site["real_name"]
    jsonld = {
        "@context": "https://schema.org",
        "@type": "MusicRecording",
        "name": entry["title"],
        "byArtist": {"@type": "MusicGroup", "name": entry["artist"]},
        "url": canonical,
        "image": f'{site["url"]}{cover}',
        "contributor": person,
        # тот же трек в Spotify. Идентификатор и раньше лежал в разметке, но
        # только внутри iframe плеера — для краулера этой связи не было
        "sameAs": f'https://open.spotify.com/track/{entry["id"]}',
    }
    # роль общим полем «contributor» видна человеку, но не машине: продюсер
    # и сведение для неё одно и то же. Что называется в schema.org своим
    # именем — называем
    if "prod" in entry["roles"]:
        jsonld["producer"] = person
    if "write" in entry["roles"]:
        jsonld["author"] = person
    if entry.get("album"):
        jsonld["inAlbum"] = {"@type": "MusicAlbum", "name": entry["album"]}
    if entry.get("year"):
        jsonld["datePublished"] = str(entry["year"])
    w = words(site)
    roles_html = "".join(f"<li>{esc(word)}</li>" for word in role_words)
    page_title = f'{title_line} · {site["name"]}'
    # ссылка на всех работах с этим артистом — усиливает страницу артиста
    # внутренними ссылками с каждого его трека
    main = main_artist(entry["artist"])
    artist_link = (f'<p><a class="back" href="/artist/{esc(slugify(main))}/">'
                   f'Все работы с {esc(main)} →</a></p>')
    crumb_html, crumb_ld = crumbs(site, [
        (w["works"], "/"), (w["hub_title"], "/track/"),
        (main, f'/artist/{slugify(main)}/'),
        (entry["title"], f'/track/{entry["slug"]}/')])
    return (
        f'{head(site, title=page_title, description=clamp(lead), canonical=canonical, image=cover)}'
        f'<div class="pf">{nav(site)}'
        f'{crumb_html}'
        f'<article class="trk">'
        f'<div class="coverbox">'
        f'<img class="cover" src="{cover}" alt="{esc(entry["artist"])} — {esc(entry["title"])}" '
        f'width="640" height="640"></div>'
        f'<div><h1>{caps_line(title_line)}</h1>'
        + "".join(f'<p class="lead">{esc(part)}</p>'
                  for part in re.split(r"\n\s*\n", lead.strip()) if part.strip())
        + (
        f'<ul class="roles">{roles_html}</ul>'
        f'<iframe class="embed" title="{esc(entry["title"])} — Spotify" loading="lazy" '
        f'src="https://open.spotify.com/embed/track/{esc(entry["id"])}?theme=0" '
        f'allow="encrypted-media"></iframe>'
        f'{artist_link}'
        f'<p><a class="back" href="/track/">{esc(w["all_tracks"])} →</a></p>'
        f'</div></article></div>'
        f'{footer(site)}'
        f'{ld_script(jsonld, crumb_ld)}'
        f'</body></html>'))


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


def letter_id(group, ch):
    """Якорь буквы указателя. Группа в id обязательна: slugify латинизирует
    кириллицу, и «А» без неё получала тот же id, что «A», — ссылка уводила
    в чужую секцию."""
    return f'l-{group}-{slugify(ch) or "n"}'


def artist_groups(entries):
    """Треки по главному артисту — та же группировка, что и в catalog().

    Гость дуэта своей страницы не получает, только упоминание у главного —
    так уже устроен каталог, страница артиста продолжает то же правило.
    """
    groups = {}
    for e in entries:
        groups.setdefault(main_artist(e["artist"]), []).append(e)
    return groups


def render_artist_page(site, artist, tracks, alias=None):
    """Страница артиста: прямой ответ на «кто сводит/продюсирует <артист>».

    Точечные страницы треков отвечают на запрос про конкретную песню,
    а вот кто вообще работает с артистом — искали и не находили: ни у одной
    страницы не было заголовка и тела текста именно под такой вопрос.
    """
    w = words(site)
    slug = slugify(artist)
    canonical = f'{site["url"]}/artist/{slug}/'
    roles_all = set()
    for t in tracks:
        roles_all |= set(t.get("roles") or [])
    role = primary_role(site, list(roles_all))
    verb = site["roles"].get(role, {}).get("verb") or "Кто работал с"
    # алиас кириллицей рядом с рабочим именем — так текст страницы совпадает
    # и с латинским, и с русским написанием одного и того же артиста
    display = f'{artist} ({alias})' if alias else artist
    # имя после тире, не как дополнение глагола: «Асию» вместо «Асия» никто
    # не посчитает для полусотни артистов, а тире снимает вопрос падежа —
    # тот же приём уже работает в заголовке страницы трека
    title_line = f'{verb} треки — {display}'
    role_words = [site["roles"][r]["word"] for r in config.ROLE_ORDER
                  if r in roles_all and r in site["roles"]]
    who = ", ".join(role_words).lower()
    n = len(tracks)
    lead = (f'{credit_name(site)} — {who.capitalize()}: {n} '
            f'{plural(n, w["tracks_word"])}.')
    ordered = sorted(
        tracks, key=lambda t: (-(int(t["year"]) if t.get("year") else 0), t["title"]))
    rows = []
    for t in ordered:
        t_roles = ", ".join(
            site["roles"][r]["word"] for r in config.ROLE_ORDER
            if r in (t.get("roles") or []) and r in site["roles"]).lower()
        year = f' · {esc(t["year"])}' if t.get("year") else ""
        rows.append(f'<li><a href="/track/{esc(t["slug"])}/">{esc(t["title"])}'
                    f'<span class="yr">{esc(t_roles)}{year}</span></a></li>')
    page_title = f'{title_line} · {site["name"]}'
    desc = clamp(f'{title_line}. {lead}')
    about = {"@type": "Person", "name": site["name"], "url": f'{site["url"]}/'}
    if site.get("real_name"):
        about["alternateName"] = site["real_name"]
    jsonld = {
        "@context": "https://schema.org",
        "@type": "ProfilePage",
        "url": canonical,
        "name": page_title,
        "description": desc,
        "about": about,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": n,
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1,
                 "url": f'{site["url"]}/track/{t["slug"]}/', "name": t["title"]}
                for i, t in enumerate(ordered)],
        },
    }
    crumb_html, crumb_ld = crumbs(site, [
        (w["works"], "/"), (w["hub_title"], "/track/"),
        (display, f'/artist/{slug}/')])
    return (
        f'{head(site, title=page_title, description=desc, canonical=canonical)}'
        f'<div class="pf">{nav(site)}'
        f'{crumb_html}'
        f'<div class="hub"><h1>{caps_line(title_line)}</h1>'
        f'<p class="lead">{esc(lead)}</p>'
        f'<ul>{"".join(rows)}</ul></div></div>'
        f'{footer(site)}'
        f'{ld_script(jsonld, crumb_ld)}'
        f'</body></html>')


# Значки площадок. Рисуем сами и одним цветом: чужие фирменные файлы —
# это и лишние запросы, и чужие права. Внутри одной сетки 24×24 и одной
# толщины линии набор смотрится своим, а не наклейками с разных сайтов.
SOCIAL_ICONS = {
    "telegram": '<path d="M21.7 4.3 2.9 11.5c-1 .4-1 1.8.1 2.1l4.6 1.4 1.8 5.4c.3.8 1.3 1 1.9.4'
                'l2.5-2.4 4.6 3.4c.7.5 1.7.1 1.9-.8l3.3-15.3c.2-1-.8-1.8-1.9-1.4zM9.4 15.2l8.2-5.6'
                '-6.6 6.6-.2 3.1-1.4-4.1z"/>',
    "instagram": '<rect x="3.2" y="3.2" width="17.6" height="17.6" rx="5" fill="none" '
                 'stroke="currentColor" stroke-width="1.7"/>'
                 '<circle cx="12" cy="12" r="4.1" fill="none" stroke="currentColor" stroke-width="1.7"/>'
                 '<circle cx="17.2" cy="6.9" r="1.25"/>',
    "spotify": '<circle cx="12" cy="12" r="9.1" fill="none" stroke="currentColor" stroke-width="1.7"/>'
               '<path d="M7.3 9.5c3.1-.9 6.7-.5 9.4 1M7.9 12.7c2.6-.7 5.5-.4 7.7.9'
               'M8.5 15.8c2-.5 4.2-.3 5.9.7" fill="none" stroke="currentColor" '
               'stroke-width="1.6" stroke-linecap="round"/>',
    "yandex": '<circle cx="12" cy="12" r="9.1" fill="none" stroke="currentColor" stroke-width="1.7"/>'
              '<path d="M10.3 15.4V8.7l5-1.3v6" fill="none" stroke="currentColor" '
              'stroke-width="1.7" stroke-linecap="round"/>'
              '<circle cx="8.9" cy="15.6" r="1.7"/><circle cx="13.6" cy="14.3" r="1.7"/>',
    # у VK знак — это буквы в скруглённом квадрате, и квадрат там залит,
    # а буквы вырезаны. Контурная версия на него не похожа, поэтому здесь
    # заливка, а буквы цветом фона. Рисуем путями, а не текстом: шрифт
    # может не подгрузиться, путь нарисуется всегда
    "vk": '<rect x="2.9" y="2.9" width="18.2" height="18.2" rx="5.4"/>'
          '<path d="M5.9 8.7h2.15l1.6 4.3 1.6-4.3h2.15l-2.75 6.6h-1.9z" fill="var(--bg)"/>'
          '<path d="M13.15 8.7h1.95v6.6h-1.95z" fill="var(--bg)"/>'
          '<path d="M15.1 11.9l1.95-3.2h2.2l-2.35 3.6 2.5 3h-2.25z" fill="var(--bg)"/>',
}


def social_row(site):
    """Значки площадок. Показываем те профили, для которых есть значок."""
    parts = []
    for link in all_links(site):
        icon = SOCIAL_ICONS.get((link.get("icon") or "").lower())
        if not icon:
            continue
        parts.append(
            f'<a href="{esc(link["url"])}" target="_blank" rel="me noopener" '
            f'aria-label="{esc(link["label"])}">'
            f'<svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" '
            f'aria-hidden="true" focusable="false">{icon}</svg>'
            f'<span class="sr-only">{esc(link["label"])}</span></a>')
    return f'<p class="social">{"".join(parts)}</p>' if parts else ""


def all_links(site):
    """Ссылки на себя в других местах: профили плюс то, что в шапке.

    Профили идут первыми, повторы по адресу выкидываются — иначе Telegram,
    который есть и там, и там, ушёл бы в sameAs дважды.
    """
    seen, out = set(), []
    for link in (site.get("profiles") or []) + (site.get("links") or []):
        url = (link.get("url") or "").strip()
        if url.startswith("http") and url not in seen:
            seen.add(url)
            out.append(link)
    return out


def person_ld(site, about=None):
    """Person для разметки. Один и тот же @id на главной и на /about/."""
    who = {"@context": "https://schema.org", "@type": "Person",
           "@id": f'{site["url"]}/#person',
           "name": site["name"], "url": f'{site["url"]}/',
           "jobTitle": site["tagline"]}
    if site.get("real_name"):
        who["alternateName"] = site["real_name"]
    photo = (about or {}).get("photo")
    who["image"] = f'{site["url"]}{photo or site.get("og_image", "")}'
    same_as = [l["url"] for l in all_links(site)]
    if same_as:
        who["sameAs"] = same_as
    email = next((c["url"][7:] for c in site.get("contacts") or []
                  if c.get("url", "").startswith("mailto:")), None)
    if email:
        who["email"] = email
    return who


def render_about(site, about, data, entries, groups):
    """Страница про человека, а не про каталог.

    До неё настоящее имя жило только в мета-тегах и разметке: в видимом
    тексте сайта «Артем Ткачев» не встречался ни разу, и запросу по имени
    приземляться было некуда. Здесь у имени есть заголовок, абзац и адрес,
    на который ссылаются профили на других площадках.

    Цифры не пишутся руками: треки, артисты и годы считаются из данных,
    поэтому устареть после следующего релиза им негде.
    """
    w = words(site)
    canonical = f'{site["url"]}/about/'
    heading = about.get("heading") or (
        f'{site.get("real_name") or site["name"]} — {site["tagline"]}')
    subhead = about.get("subhead") or (
        f'Работает под именем {site["name"]}' if site.get("real_name") else "")
    years = sorted(int(e["year"]) for e in entries if e.get("year"))
    # альбомы считаем так же, как каталог: релизами, а не названиями из
    # треков. Иначе сингл, вышедший в чужой альбом, добавляет шестой
    albums = len([r for r in data["releases"] if r["type"] == "album"])
    # плитки с цифрами: сначала то, что нельзя посчитать из данных
    # (прослушивания приходят с площадок и указываются руками, с источником),
    # потом наше — оно пересчитывается на каждой сборке и устареть не может
    manual = [(str(n.get("value", "")), n.get("label", ""))
              for n in about.get("numbers") or []]
    auto = [(str(len(entries)), "треков"), (str(len(groups)), "артистов")]
    if albums:
        auto.append((str(albums), "альбомов"))
    if years:
        auto.append((f'{years[0]}—{years[-1]}', "годы работ"))
    # заданные руками цифры отменяют автоматические целиком: если человек
    # перечислил, что показывать, дописывать к этому своё — спорить с ним.
    # Ряд держим в четыре плитки, пятая уезжает на вторую строку и висит
    # там одна
    tiles = (manual or auto)[:4]
    # длинное значение («2021—2026») крупным кеглем не влезает в свою колонку
    # и переносится посреди диапазона — такому набираем помельче
    def tile(value, label):
        cls = ' class="long"' if len(value) > 7 else ""
        return f'<div{cls}><b>{esc(value)}</b><span>{esc(label)}</span></div>'

    stats = "".join(tile(v, label) for v, label in tiles if v)
    source = about.get("numbers_note") or ""
    role_words = [site["roles"][r]["word"] for r in config.ROLE_ORDER
                  if r in site["roles"] and any(r in (e.get("roles") or [])
                                                for e in entries)]
    lead = (about.get("lead") or "").strip()
    body = "".join(f'<p>{inline(par)}</p>' for par in about.get("body") or [])
    # значки живут под фотографией: там их видно сразу, и они не разрывают
    # цифры с текстом в правой колонке
    social = social_row(site)
    photo = ""
    if about.get("photo"):
        photo = (f'<div class="mephoto"><div class="coverbox"><img class="cover" '
                 f'src="{esc(about["photo"])}" '
                 f'alt="{esc(about.get("photo_alt") or site.get("real_name") or site["name"])}" '
                 f'width="640" height="640" loading="lazy"></div>{social}</div>')
    rows = []
    for artist, tracks in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        n = len(tracks)
        rows.append(f'<li><a href="/artist/{esc(slugify(artist))}/">{esc(artist)}'
                    f'<span class="yr">{n} {esc(plural(n, w["tracks_word"]))}</span>'
                    f'</a></li>')
    profiles_block = ""
    cta = about.get("cta") or next(
        (c for c in site.get("contacts") or [] if c.get("primary")), None)
    cta_block = (f'<p><a class="cta" href="{esc(cta["url"])}" target="_blank" '
                 f'rel="noopener">{esc(cta.get("label") or w["contact"])} →</a></p>'
                 if cta else "")
    # в тексте работает мини-разметка, в описании для поиска её быть не должно
    desc = clamp(plain(lead) if lead else f'{heading}. {subhead}')
    page_title = f'{heading} · {site["name"]}'
    crumb_html, crumb_ld = crumbs(site, [(w["works"], "/"), (w["about"], "/about/")])
    who = person_ld(site, about)
    who.pop("@context", None)
    jsonld = {"@context": "https://schema.org", "@type": "ProfilePage",
              "url": canonical, "name": page_title, "description": desc,
              "inLanguage": site["lang"], "mainEntity": who}
    return (
        f'{head(site, title=page_title, description=desc, canonical=canonical, image=about.get("photo"))}'
        f'<div class="pf">{nav(site)}'
        f'{crumb_html}'
        f'<article class="trk">{photo}'
        f'<div><h1>{caps_line(heading)}</h1>'
        + (f'<p class="sub">{esc(subhead)}</p>' if subhead else "")
        + (f'<div class="nums">{stats}</div>' if stats else "")
        + ("" if photo else social)
        + (f'<p class="numsrc">{esc(source)}</p>' if source else "")
        + (f'<p class="lead">{inline(lead)}</p>' if lead else "")
        + body
        + (f'<ul class="roles">'
           + "".join(f"<li>{esc(word)}</li>" for word in role_words)
           + '</ul>' if role_words else "")
        + f'{cta_block}</div></article>'
        f'<div class="hub me"><h2>{esc(w["worked_with"])}</h2>'
        f'<ul>{"".join(rows)}</ul>'
        f'{profiles_block}</div></div>'
        f'{footer(site)}'
        f'{ld_script(jsonld, crumb_ld)}'
        f'</body></html>')


def catalog(site, data, entries):
    """Артисты по алфавиту, у каждого — альбомы и отдельно синглы."""
    slug_of = {e["id"]: e["slug"] for e in entries}
    shelf = {}
    for rel in order_releases(site, data["releases"], include_hidden=True):
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
            letters.append((group, ch))
            blocks.append(f'<h2 class="ltr" id="{esc(letter_id(group, ch))}">'
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
            f'<h3><a href="/artist/{esc(slugify(artist))}/">{esc(artist)}</a>'
            f'<span class="cnt">{n}</span></h3>'
            f'{"".join(parts)}</section>')

    nav_letters = "".join(
        f'<a href="#{esc(letter_id(g, ch))}">{esc(ch)}</a>' for g, ch in letters)

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
            f'{w["catalog_lead"]}: {scope}. {w["catalog_hint"]}')
    desc = clamp(desc)
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
    crumb_html, crumb_ld = crumbs(site, [
        (w["works"], "/"), (w["hub_title"], "/track/")])
    return (
        f'{head(site, title=page_title, description=desc, canonical=canonical)}'
        f'<div class="pf hub">{nav(site)}'
        f'{crumb_html}'
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
        f'{ld_script(jsonld, crumb_ld)}'
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


#: сколько символов поисковик показывает в описании, дальше — многоточие
META_MAX = 160


def clamp(text, limit=META_MAX):
    """Описание не длиннее limit, но обрезанное по-человечески.

    Сначала пробуем закончить на точке — тогда описание выглядит как
    законченная мысль, а не как оборванная строка. Если целого предложения
    не помещается, режем по границе слова и ставим многоточие. Раньше здесь
    был срез [:300], и описание FAQ обрывалось посреди имени: «VERBEE, Kla».
    """
    out = " ".join(str(text or "").split())
    if len(out) <= limit:
        return out
    head = out[:limit + 1]
    stop = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if stop >= limit * 0.55:
        return head[:stop + 1].strip()
    cut = head.rfind(" ")
    return head[:cut].rstrip(" ,;:—-") + "…"


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
    desc = clamp(plain(faq.get("summary") or ""))
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

    w = words(site)
    crumb_html, crumb_ld = crumbs(site, [(w["works"], "/"), (w["faq"], "/faq/")])
    return (
        f'{head(site, title=title, description=desc, canonical=canonical)}'
        f'<div class="pf faq">{nav(site)}'
        f'{crumb_html}'
        f'<h1>{esc(faq.get("heading") or "Вопросы и ответы")}</h1>'
        + (f'<p class="lead">{inline(faq["intro"])}</p>' if faq.get("intro") else "")
        + f'{summary}'
        f'<nav class="faqtabs" aria-label="Разделы">{tabs}</nav>'
        f'{"".join(blocks)}{updated}</div>'
        f'{footer(site)}'
        f'{ld_script(jsonld, crumb_ld)}'
        f'</body></html>')


LASTMOD_FILE = "lastmod.json"


def _git_date(out, rel_path):
    """Когда файл менялся по истории репозитория."""
    try:
        res = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(rel_path)],
            cwd=str(out), text=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    stamp = res.stdout.strip()
    return stamp if len(stamp) == 10 else None


def update_lastmod(out, pages):
    """Настоящие даты изменения страниц — для sitemap.

    Раньше в карту сайта шла дата сборки, одна на все страницы. Пересборка
    из-за запятой в одном ответе объявляла изменившимися все сто тридцать,
    и поисковику оставалось только перестать верить полю целиком: Google
    учитывает lastmod, пока тот похож на правду.

    Дата меняется, только когда изменилось содержимое страницы — сверяем
    хеш с прошлой сборкой. Снимок лежит рядом с сайтом и уезжает в
    репозиторий: без него сборка на чистой копии объявит новым всё разом.

    Возвращает (даты по адресам, список изменившихся адресов).
    """
    out = Path(out)
    store = out / LASTMOD_FILE
    try:
        old = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    today = date.today().isoformat()
    fresh, changed = {}, []
    for url, path in pages.items():
        digest = hashlib.sha1(Path(path).read_bytes()).hexdigest()[:16]
        was = old.get(url) or {}
        if was.get("hash") == digest:
            fresh[url] = was
            continue
        # первый запуск: даты берём из истории репозитория, иначе объявим
        # сегодняшними сто тридцать страниц, которые не менялись месяцами
        stamp = today if was else (_git_date(out, Path(path).relative_to(out)) or today)
        fresh[url] = {"hash": digest, "date": stamp}
        if stamp == today:
            changed.append(url)
    store.write_text(json.dumps(fresh, ensure_ascii=False, indent=1, sort_keys=True),
                     encoding="utf-8")
    return fresh, changed


def render_sitemap(site, urls, dates):
    today = date.today().isoformat()
    body = "".join(
        f'<url><loc>{esc(u)}</loc>'
        f'<lastmod>{esc((dates.get(u) or {}).get("date") or today)}</lastmod></url>'
        for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{body}</urlset>")


def _rfc822(stamp):
    """Дата для RSS: там свой формат, ISO не примут."""
    try:
        d = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
    except ValueError:
        d = datetime.now(timezone.utc)
    return d.strftime("%a, %d %b %Y %H:%M:%S +0000")


def render_feed(site, entries, dates, limit=30):
    """Лента последних работ: её читают агрегаторы и часть краулеров.

    Порядок — по дате изменения страницы, то есть сверху то, что недавно
    появилось или переписано. Дат выхода трека с точностью до дня у нас нет,
    в данных только год, и выдумывать их ради ленты незачем.
    """
    rows = []
    for e in entries:
        url = f'{site["url"]}/track/{e["slug"]}/'
        stamp = (dates.get(url) or {}).get("date") or date.today().isoformat()
        rows.append((stamp, url, e))
    rows.sort(key=lambda r: (r[0], r[2]["title"]), reverse=True)
    items = "".join(
        f'<item><title>{esc(e["artist"])} — {esc(e["title"])}</title>'
        f'<link>{esc(url)}</link>'
        f'<guid isPermaLink="true">{esc(url)}</guid>'
        f'<pubDate>{_rfc822(stamp)}</pubDate>'
        f'<description>{esc((e.get("about") or "").strip() or auto_lead(site, e))}'
        f'</description></item>'
        for stamp, url, e in rows[:limit])
    desc = site.get("description") or f'{site["name"]} — {site["tagline"]}'
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            f'<title>{esc(site["name"])} — {esc(words(site)["hub_title"]).lower()}</title>'
            f'<link>{esc(site["url"])}/</link>'
            f'<description>{esc(desc)}</description>'
            f'<language>{esc(site["lang"])}</language>'
            f'<atom:link href="{esc(site["url"])}/feed.xml" rel="self" '
            f'type="application/rss+xml"/>'
            f'<lastBuildDate>{_rfc822(date.today().isoformat())}</lastBuildDate>'
            f'{items}</channel></rss>')


def render_robots(site):
    return f"User-agent: *\nAllow: /\n\nSitemap: {site['url']}/sitemap.xml\n"


def render_llms(site, data, entries, groups=None, aliases=None):
    """llms.txt — краткая карта сайта для ИИ-поисковиков (llmstxt.org).

    Не заменяет sitemap.xml для обычного поиска: это отдельный, человеко- и
    ИИ-читаемый файл с готовым списком «кто над чем работал», без разбора
    HTML-вёрстки.
    """
    aliases = aliases or {}
    lead = site.get("description") or f'{site["name"]} — {site["tagline"]}'
    lines = [f'# {site["name"]}', "", f'> {lead}', ""]
    if site.get("real_name"):
        lines.append(f'Рабочее имя {site["name"]} принадлежит {site["real_name"]}.')
        lines.append("")
    lines.append("## Разделы")
    lines.append(f'- [Работы]({site["url"]}/): витрина обложек с плеером, '
                 f'фильтры по жанру и роли')
    lines.append(f'- [Каталог]({site["url"]}/track/): работы по алфавиту '
                 f'артиста, поиск по артисту, альбому или треку')
    lines.append("")
    lines.append("Каталог неполный: на сайте собрана только часть работ.")
    if site.get("has_about"):
        lines.append(f'- [О себе]({site["url"]}/about/): кто это, чем занимается, '
                     f'профили на других площадках')
    if site.get("has_faq"):
        lines.append(f'- [Вопросы и ответы]({site["url"]}/faq/)')
    lines.append("")
    if groups:
        lines.append("## Артисты")
        for artist in sorted(groups, key=str.upper):
            alias = f' / {aliases[artist]}' if aliases.get(artist) else ""
            lines.append(f'- [{artist}{alias}]'
                         f'({site["url"]}/artist/{slugify(artist)}/): '
                         f'{len(groups[artist])} {plural(len(groups[artist]), words(site)["tracks_word"])}')
        lines.append("")
    lines.append("## Треки")
    for e in entries:
        role_words = [site["roles"][r]["word"] for r in config.ROLE_ORDER
                      if r in e["roles"] and r in site["roles"]]
        roles = ", ".join(role_words).lower()
        year = f', {e["year"]}' if e.get("year") else ""
        lines.append(f'- [{e["artist"]} — {e["title"]}]'
                     f'({site["url"]}/track/{e["slug"]}/): {roles}{year}')
    return "\n".join(lines) + "\n"


def render_site(site, data, out_dir, faq=None, artist_names=None, about=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _PAGES.clear()
    site = dict(site, has_faq=bool(faq), has_about=bool(about),
                logo_svg=load_logo_svg(site, out_dir))
    entries = track_entries(site, data)
    # адрес → файл: по ним считаются даты изменения для карты сайта
    pages = {}
    (out / "index.html").write_text(
        render_index(site, data, entries), encoding="utf-8")
    pages[f'{site["url"]}/'] = out / "index.html"
    track_dir = out / "track"
    track_dir.mkdir(exist_ok=True)
    (track_dir / "index.html").write_text(
        render_hub(site, data, entries), encoding="utf-8")
    pages[f'{site["url"]}/track/'] = track_dir / "index.html"
    for entry in entries:
        page_dir = track_dir / entry["slug"]
        page_dir.mkdir(exist_ok=True)
        (page_dir / "index.html").write_text(
            render_track_page(site, entry), encoding="utf-8")
        pages[f'{site["url"]}/track/{entry["slug"]}/'] = page_dir / "index.html"
    aliases = artist_names or {}
    groups = artist_groups(entries)
    artist_dir = out / "artist"
    artist_dir.mkdir(exist_ok=True)
    artist_urls = []
    for artist, tracks in groups.items():
        slug = slugify(artist)
        page_dir = artist_dir / slug
        page_dir.mkdir(exist_ok=True)
        (page_dir / "index.html").write_text(
            render_artist_page(site, artist, tracks, alias=aliases.get(artist)),
            encoding="utf-8")
        artist_urls.append(f'{site["url"]}/artist/{slug}/')
        pages[f'{site["url"]}/artist/{slug}/'] = page_dir / "index.html"
    extra = list(artist_urls)
    if about:
        about_dir = out / "about"
        about_dir.mkdir(exist_ok=True)
        (about_dir / "index.html").write_text(
            render_about(site, about, data, entries, groups), encoding="utf-8")
        extra.append(f'{site["url"]}/about/')
        pages[f'{site["url"]}/about/'] = about_dir / "index.html"
    if faq:
        faq_dir = out / "faq"
        faq_dir.mkdir(exist_ok=True)
        (faq_dir / "index.html").write_text(render_faq(site, faq), encoding="utf-8")
        extra.append(f'{site["url"]}/faq/')
        pages[f'{site["url"]}/faq/'] = faq_dir / "index.html"
    dates, changed = update_lastmod(out, pages)
    sitemap_urls = ([f'{site["url"]}/', f'{site["url"]}/track/'] + extra
                    + [f'{site["url"]}/track/{e["slug"]}/' for e in entries])
    (out / "sitemap.xml").write_text(
        render_sitemap(site, sitemap_urls, dates), encoding="utf-8")
    (out / "feed.xml").write_text(
        render_feed(site, entries, dates), encoding="utf-8")
    # ключ IndexNow: сервис скачивает его из корня и убеждается, что список
    # изменившихся адресов присылает владелец сайта, а не посторонний
    key = site.get("indexnow_key")
    if key:
        (out / f"{key}.txt").write_text(key, encoding="utf-8")
    (out / "robots.txt").write_text(render_robots(site), encoding="utf-8")
    (out / "llms.txt").write_text(
        render_llms(site, data, entries, groups, aliases), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    found = checks.run(site, data, faq, _PAGES, out_dir=out,
                       slugs=[e["slug"] for e in entries])
    return {"tracks": len(entries),
            "changed": changed,
            # считаем всё собранное: у скрытой работы страница тоже есть
            "releases": len(data["releases"]),
            "off_grid": len([r for r in data["releases"] if r.get("hidden")]),
            "faq": sum(len(s.get("items") or []) for s in (faq or {}).get("sections") or []),
            "checks": checks.report(found),
            "blocking": len(checks.blocking(found))}
