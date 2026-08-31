"""Данные о релизах из Spotify — без ключей, через открытые адреса.

Портировано из скилла credits-add-track: тот же oEmbed + разбор страницы
эмбеда. Публичный эмбед плейлиста отдаёт примерно первые 100 треков.
"""
import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}

URL_RE = re.compile(
    r"open\.spotify\.com/(?:intl-[a-z]{2}/)?(track|album|playlist)/([A-Za-z0-9]{22})")
COVER_RE = re.compile(r"ab67616d[0-9a-f]{8}([0-9a-f]+)")


class SpotifyError(Exception):
    pass


def parse_url(url):
    """('track'|'album'|'playlist', id) из любой ссылки Spotify."""
    m = URL_RE.search(url)
    if not m:
        raise ValueError(
            f"это не ссылка на трек, альбом или плейлист Spotify: {url!r}")
    return m.group(1), m.group(2)


def cover_hash(thumb_url):
    m = COVER_RE.search(thumb_url or "")
    if not m:
        raise ValueError(f"не удалось разобрать обложку: {thumb_url!r}")
    return m.group(1)


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8")


def _next_data(page):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    return json.loads(m.group(1)) if m else {}


def _find(obj, key, depth=0):
    if depth > 9:
        return None
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _find(value, key, depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find(value, key, depth + 1)
            if found is not None:
                return found
    return None


def oembed(kind, sid):
    url = urllib.parse.quote(f"https://open.spotify.com/{kind}/{sid}")
    return json.loads(_get(f"https://open.spotify.com/oembed?url={url}"))


def fetch_track(track_id):
    oe = oembed("track", track_id)
    chash = cover_hash(oe.get("thumbnail_url"))
    artist = year = ""
    try:
        page = _get(f"https://open.spotify.com/embed/track/{track_id}")
        am = re.search(r'"artists":(\[.*?\])', page)
        if am:
            artist = ", ".join(
                a.get("name", "") for a in json.loads(am.group(1)) if a.get("name"))
        ym = re.search(r'"releaseDate":\{"isoString":"(\d{4})', page)
        if ym:
            year = ym.group(1)
    except Exception:
        pass
    return {"id": track_id, "title": oe.get("title", ""), "artist": artist,
            "year": year, "cover": chash}


def fetch_album(album_id):
    oe = oembed("album", album_id)
    chash = cover_hash(oe.get("thumbnail_url"))
    page = _get(f"https://open.spotify.com/embed/album/{album_id}")
    doc = _next_data(page)
    entity = (((doc.get("props") or {}).get("pageProps") or {})
              .get("state", {}).get("data", {}).get("entity", {}))
    track_list = entity.get("trackList") or _find(doc, "trackList") or []
    if not track_list:
        raise SpotifyError("не удалось прочитать список треков альбома")
    ym = re.search(r'"releaseDate":\{"isoString":"(\d{4})', page)
    year = ym.group(1) if ym else ""
    ids = [t["uri"].split(":")[-1] for t in track_list if t.get("uri")]
    if not year and ids:
        year = fetch_track(ids[0]).get("year", "")
    tracks = [{"id": t["uri"].split(":")[-1], "title": t.get("title", ""),
               "artist": t.get("subtitle", "")}
              for t in track_list if t.get("uri")]
    artist = entity.get("subtitle", "")
    if not artist:
        subs = [t.get("subtitle", "") for t in track_list if t.get("subtitle")]
        artist = subs[0].split(",")[0].strip() if subs else ""
    return {"album_id": album_id, "title": oe.get("title", ""), "artist": artist,
            "year": year, "cover": chash, "tracks": tracks}


def fetch_playlist(playlist_id):
    doc = _next_data(_get(f"https://open.spotify.com/embed/playlist/{playlist_id}"))
    track_list = _find(doc, "trackList") or []
    if not track_list:
        raise SpotifyError("не удалось прочитать список треков плейлиста")
    tracks = [{"id": t["uri"].split(":")[-1], "title": t.get("title", ""),
               "artist": t.get("subtitle", "")}
              for t in track_list if t.get("uri")]
    return {"name": oembed("playlist", playlist_id).get("title", ""),
            "tracks": tracks}
