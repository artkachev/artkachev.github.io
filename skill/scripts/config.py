"""Чтение и проверка настроек проекта-портфолио."""
import json
import re
from pathlib import Path

REQUIRED_SITE = ("slug", "repo", "url", "name", "tagline", "roles", "contacts")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

SITE_DEFAULTS = {
    "lang": "ru",
    "description": "",
    "logo": None,
    "og_image": None,
    "links": [],
    "genres": [],
    "featured": [],
    "facts": [],
    "analytics": None,
}
THEME_DEFAULTS = {
    "bg": "#12100f",
    "accent": "#e0563f",
    "mode": "dark",
    "font_head": "Oswald",
    "font_body": "Golos Text",
}

# Порядок важности ролей: первая найденная становится заголовком страницы трека.
ROLE_ORDER = ("write", "prod", "mix", "master")


class ConfigError(Exception):
    pass


def load_site_dict(raw):
    for key in REQUIRED_SITE:
        if not raw.get(key):
            raise ConfigError(f"в site.json нет обязательного поля: {key}")
    if not REPO_RE.match(raw["repo"]):
        raise ConfigError(
            f"repo должен быть в виде владелец/название, а не {raw['repo']!r}")
    site = dict(SITE_DEFAULTS)
    site.update(raw)
    theme = dict(THEME_DEFAULTS)
    theme.update(raw.get("theme") or {})
    site["theme"] = theme
    site["url"] = site["url"].rstrip("/")
    return site


def load_site(path):
    return load_site_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def load_data_dict(raw):
    releases = raw.get("releases")
    if releases is None:
        raise ConfigError("в data.json нет списка releases")
    seen = set()
    for rel in releases:
        rel.setdefault("type", "single")
        rel.setdefault("roles", ["mix"])
        rel.setdefault("feat", [])
        rel.setdefault("hidden", False)
        if rel["type"] == "album":
            key = ("album", rel.get("album_id"))
            for tr in rel.get("tracks", []):
                tr.setdefault("roles", list(rel["roles"]))
        else:
            key = ("single", rel.get("id"))
        if not key[1]:
            raise ConfigError(f"у релиза нет идентификатора: {rel.get('title')!r}")
        if key in seen:
            raise ConfigError(f"дубль релиза: {key[1]}")
        seen.add(key)
    return {"releases": releases}


def load_data(path):
    return load_data_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_data(path, data):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
