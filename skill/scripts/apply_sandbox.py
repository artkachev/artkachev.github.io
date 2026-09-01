"""Перенос правок из песочницы в данные сайта.

Роли уходят в roles.txt, а не в data.json: иначе следующий прогон списка
их вернёт. Всё остальное — описания, жанр, видимость — прямо в data.json.
"""
import json
import re
from pathlib import Path

import render

SKIP = ("artist", "title")


def _targets(site, data):
    """Слаг страницы → (релиз, трек или None)."""
    by_id = {e["id"]: e["slug"] for e in render.track_entries(site, data)}
    out = {}
    for rel in data["releases"]:
        if rel["type"] == "album":
            for tr in rel.get("tracks") or []:
                slug = by_id.get(tr.get("id"))
                if slug:
                    out[slug] = (rel, tr)
        else:
            slug = by_id.get(rel.get("id"))
            if slug:
                out[slug] = (rel, None)
    return out


def _roles_line(site, title, artist, roles):
    words = [site["roles"][r]["word"] for r in ("write", "prod", "mix", "master")
             if r in roles and r in site["roles"]]
    return f'{title} — {artist} — {", ".join(words)}'


def _rewrite_roles(path, site, wanted):
    """wanted: список (название, артист, роли). Строки правим на месте."""
    lines = path.read_text(encoding="utf-8").splitlines()
    done, touched = set(), 0
    for n, line in enumerate(lines):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        parts = [p.strip() for p in raw.replace("—", "-").split(" - ")]
        if len(parts) < 3:
            continue
        title = " - ".join(parts[:-2]).lower()
        artist = parts[-2].lower()
        for key, (t, a, roles) in enumerate(wanted):
            if key in done:
                continue
            if title == t.lower() and artist == a.lower():
                lines[n] = _roles_line(site, t, a, roles)
                done.add(key)
                touched += 1
    for key, (t, a, roles) in enumerate(wanted):
        if key not in done:
            lines.append(_roles_line(site, t, a, roles))
            touched += 1
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return touched


def apply(proj, site, data, state):
    proj = Path(proj)
    targets = _targets(site, data)
    changed, roles_wanted, missed = [], [], []

    for slug, edit in (state.get("edits") or {}).items():
        hit = targets.get(slug)
        if not hit:
            missed.append(slug)
            continue
        rel, tr = hit
        node = tr or rel
        for field in ("about", "genre", "hidden"):
            if field in edit:
                value = edit[field]
                if isinstance(value, str) and not value.strip():
                    node.pop(field, None) if field == "about" else None
                    if field != "about":
                        node[field] = value
                else:
                    node[field] = value
                changed.append(f'{slug}: {field}')
        if "roles" in edit:
            roles_wanted.append((rel["title"], rel["artist"], edit["roles"]))
            changed.append(f'{slug}: роли')
        for i, patch in (edit.get("tracks") or {}).items():
            track = (rel.get("tracks") or [])[int(i)]
            if "about" in patch:
                if patch["about"].strip():
                    track["about"] = patch["about"]
                else:
                    track.pop("about", None)
                changed.append(f'{slug}/{track["title"]}: описание')
            if "roles" in patch:
                roles_wanted.append((track["title"],
                                     track.get("artist") or rel["artist"],
                                     patch["roles"]))
                changed.append(f'{slug}/{track["title"]}: роли')

    lines = 0
    if roles_wanted:
        lines = _rewrite_roles(proj / "roles.txt", site, roles_wanted)
    return {"changed": changed, "roles_lines": lines,
            "unmatched": missed,
            "imports": [a for a in (state.get("adds") or [])]}
