"""Черновик сайта одной страницей: каталог, правка ролей, очередь новых треков.

Страница живёт артефактом на claude.ai и там же хранит правки — со стороны
сайта она ничего не меняет. Обложки вшиваются миниатюрами: внешние запросы
со страницы артефакта запрещены, ссылки на covers/ оттуда не загрузятся.
"""
import base64
import json
import re
import subprocess
import tempfile
from pathlib import Path

import render

THUMB = 72          # сторона миниатюры, px
QUALITY = 45        # качество jpeg для sips


def _thumbs(proj, hashes):
    """Уменьшенные обложки в data-URI. Без sips (не macOS) — пропускаем."""
    out = {}
    covers = Path(proj) / "covers"
    with tempfile.TemporaryDirectory() as tmp:
        for h in hashes:
            src = covers / (h + ".jpg")
            if not h or not src.exists():
                continue
            dst = Path(tmp) / (h + ".jpg")
            done = subprocess.run(
                ["sips", "-Z", str(THUMB), "-s", "formatOptions", str(QUALITY),
                 str(src), "--out", str(dst)],
                capture_output=True)
            blob = dst if (done.returncode == 0 and dst.exists()) else src
            out[h] = "data:image/jpeg;base64," + base64.b64encode(
                blob.read_bytes()).decode()
    return out


def catalog(proj, site, data):
    # слаги и автоописания берём у сборщика, а не считаем заново:
    # он разводит совпадения названий, и адрес страницы знает только он
    pages = {}
    for e in render.track_entries(site, data):
        pages[e["id"]] = {"slug": e["slug"], "auto": render.auto_lead(site, e)}

    def page(key):
        return pages.get(key) or {"slug": "", "auto": ""}

    items = []
    for rel in data["releases"]:
        own = page(rel.get("id"))
        items.append({
            "type": rel["type"], "artist": rel["artist"], "title": rel["title"],
            "year": rel.get("year"), "genre": rel.get("genre"),
            "roles": rel.get("roles") or [], "hidden": bool(rel.get("hidden")),
            "cover": rel.get("cover"),
            "slug": own["slug"] or render.slugify(
                f'{rel["artist"]} {rel["title"]}'),
            "auto": own["auto"],
            "about": rel.get("about") or "",
            "tracks": [{"title": t["title"],
                        "artist": t.get("artist") or rel["artist"],
                        "roles": t.get("roles") or [],
                        "slug": page(t.get("id"))["slug"],
                        "auto": page(t.get("id"))["auto"],
                        "about": t.get("about") or ""}
                       for t in (rel.get("tracks") or [])],
        })
    logo = ""
    # в site.json путь записан для веба, с ведущим слэшем: без lstrip
    # Path посчитает его абсолютным и потеряет папку проекта
    mark = Path(proj) / site.get("logo", "assets/logo.svg").lstrip("/")
    if mark.exists():
        hit = re.search(r"<svg[^>]*>(.*?)</svg>", mark.read_text(encoding="utf-8"),
                        re.S)
        logo = hit.group(1).strip() if hit else ""
    return {
        "roles": {k: v["word"] for k, v in site["roles"].items()},
        "roleOrder": [r for r in ("write", "prod", "mix", "master")
                      if r in site["roles"]],
        "genres": [{"code": c, "label": render.genre_label(site, c)}
                   for c in site.get("genres") or []],
        "logo": logo,
        "items": items,
        "covers": _thumbs(proj, [i["cover"] for i in items]),
    }


def build(proj, site, data, out, state=None):
    """Собрать страницу песочницы. state — правки, которые надо сохранить."""
    proj, out = Path(proj), Path(out)
    tpl = Path(__file__).resolve().parent.parent / "templates"
    body = tpl.joinpath("sandbox.html").read_text(encoding="utf-8")
    app = tpl.joinpath("sandbox.js").read_text(encoding="utf-8")
    cat = json.dumps(catalog(proj, site, data), ensure_ascii=False)
    st = json.dumps(state or {"edits": {}, "adds": [], "updated": None},
                    ensure_ascii=False)
    tag = "scr" + "ipt"
    doc = (body
           + f'<{tag} id="catalog" type="application/json">'
           + cat.replace("<", "\\u003c") + f"</{tag}>\n"
           + f'<{tag} id="state" type="application/json">'
           + st.replace("<", "\\u003c") + f"</{tag}>\n"
           + f'<{tag} id="app">' + app + f"</{tag}>\n")
    out.write_text(doc, encoding="utf-8")
    return {"file": str(out), "kb": round(out.stat().st_size / 1024),
            "releases": len(data["releases"])}
