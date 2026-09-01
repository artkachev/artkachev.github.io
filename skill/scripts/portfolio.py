#!/usr/bin/env python3
"""Сборка сайта-портфолио: import / build / roles / publish.

Проект — папка с site.json, data.json и собранным сайтом.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import covers
import publish as publish_mod
import render
import apply_sandbox
import sandbox
import spotify


def _project(args):
    return Path(args.project).expanduser().resolve()


def _load(proj):
    site = config.load_site(proj / "site.json")
    data_path = proj / "data.json"
    data = config.load_data(data_path) if data_path.exists() else {"releases": []}
    return site, data


def _faq(proj):
    """Вопросы и ответы — необязательный файл, без него страницы просто нет."""
    path = proj / "faq.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _genre_map(proj):
    path = proj / "artist_genres.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _artist_names(proj):
    """Кириллические написания артистов для страниц /artist/ — необязательно.

    Нужно только тем, кого официально пишут латиницей (Klava Koka), а ищут
    кириллицей («Клава Кока»): без пары в тексте страницы не будет слова,
    по которому её найдёт русский запрос.
    """
    path = proj / "artist_names.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _primary_artist(artist):
    return (artist or "").split(",")[0].strip()


def cmd_import(args):
    proj = _project(args)
    site, data = _load(proj)
    kind, sid = spotify.parse_url(args.url)
    genres = _genre_map(proj)
    known = set()
    for rel in data["releases"]:
        known.add(rel.get("id") or rel.get("album_id"))
        for tr in rel.get("tracks", []):
            known.add(tr["id"])

    incoming = []
    if kind == "playlist":
        doc = spotify.fetch_playlist(sid)
        incoming = [t for t in doc["tracks"] if t["id"] not in known]
    elif kind == "track":
        track = spotify.fetch_track(sid)
        incoming = [] if track["id"] in known else [track]
    else:
        album = spotify.fetch_album(sid)
        if album["album_id"] in known:
            incoming = []
        elif len(album["tracks"]) == 1 and not args.force_album:
            incoming = [spotify.fetch_track(album["tracks"][0]["id"])]
        else:
            rel = {"type": "album", "album_id": album["album_id"],
                   "artist": album["artist"], "title": album["title"],
                   "year": album["year"], "cover": album["cover"],
                   "genre": args.genre or genres.get(_primary_artist(album["artist"])),
                   "roles": [args.role], "hidden": False,
                   "tracks": [{"id": t["id"], "title": t["title"],
                               "artist": t["artist"], "roles": [args.role]}
                              for t in album["tracks"]]}
            data["releases"].append(rel)
            incoming = []

    unknown_genre = []
    added = 0
    for track in incoming:
        meta = track if "cover" in track else spotify.fetch_track(track["id"])
        artist = meta.get("artist") or track.get("artist") or ""
        genre = args.genre or genres.get(_primary_artist(artist))
        if not genre and site.get("genres"):
            unknown_genre.append(_primary_artist(artist))
        data["releases"].append({
            "type": "single", "id": meta["id"],
            "artist": artist, "title": meta.get("title") or track.get("title"),
            "year": meta.get("year"), "genre": genre, "roles": [args.role],
            "cover": meta.get("cover"), "feat": [], "hidden": False})
        added += 1

    data = config.load_data_dict(data)
    config.save_data(proj / "data.json", data)
    hashes = []
    for rel in data["releases"]:
        hashes.append(rel.get("cover"))
    cover_result = covers.download(proj, hashes)
    result = {"added": added, "total": len(data["releases"]),
              "covers": {k: len(v) for k, v in cover_result.items()},
              "cover_failures": cover_result["failed"],
              "unknown_genre": sorted(set(unknown_genre))}
    _out(result, args)
    return 0 if not cover_result["failed"] else 3


def cmd_roles(args):
    """Строки вида: Название — Артист — продакшн, сведение

    Читаем с конца: последний кусок — роли, предпоследний — артист,
    всё остальное склеивается обратно в название. Иначе трек вроде
    «Я не отдам тебя никому - Bonus track» разваливается по своему же тире.
    """
    proj = _project(args)
    site, data = _load(proj)
    words = {v["word"].lower(): k for k, v in site["roles"].items()}
    words.update({k: k for k in site["roles"]})

    by_pair, by_title = {}, {}
    for rel in data["releases"]:
        targets = (rel.get("tracks", []) if rel["type"] == "album" else [rel])
        for tr in targets:
            title = tr["title"].strip().lower()
            artist = (tr.get("artist") or rel["artist"]).strip().lower()
            by_pair[(title, artist)] = tr
            by_pair[(title, artist.split(",")[0].strip())] = tr
            by_title.setdefault(title, []).append(tr)

    def find(title, artist):
        """Сначала по паре название+артист, потом по одному названию."""
        if artist:
            hit = by_pair.get((title, artist)) or by_pair.get(
                (title, artist.split(",")[0].strip()))
            if hit:
                return hit
        same = by_title.get(title) or []
        return same[0] if len(same) == 1 else None

    applied, unmatched = 0, []
    for line in Path(args.file).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.replace("—", "-").split(" - ")]
        if len(parts) < 2:
            unmatched.append(line)
            continue
        role_text = parts[-1]
        artist = parts[-2] if len(parts) > 2 else ""
        title = " - ".join(parts[:-2]) if len(parts) > 2 else parts[0]

        target = find(title.lower(), artist.lower())
        roles = [words[r.strip().lower()] for r in role_text.split(",")
                 if r.strip().lower() in words]
        if not target or not roles:
            unmatched.append(line)
            continue
        target["roles"] = roles
        applied += 1
    config.save_data(proj / "data.json", data)
    _out({"applied": applied, "unmatched": unmatched}, args)
    return 0


def cmd_sandbox(args):
    """Черновик одной страницей — публикуется артефактом, сайт не трогает."""
    proj = _project(args)
    site, data = _load(proj)
    out = args.out or (proj / "sandbox.build.html")
    # правки, которые уже накопились в песочнице, переносим в новую версию
    state = None
    if args.state:
        state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    _out(sandbox.build(proj, site, data, out, state), args)
    return 0


def cmd_apply(args):
    """Перенести правки из песочницы в данные. Роли — в roles.txt."""
    proj = _project(args)
    site, data = _load(proj)
    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    result = apply_sandbox.apply(proj, site, data, state)
    config.save_data(proj / "data.json", data)
    _out(result, args)
    return 0


def cmd_build(args):
    proj = _project(args)
    site, data = _load(proj)
    summary = render.render_site(site, data, proj, faq=_faq(proj), artist_names=_artist_names(proj))
    _out(summary, args)
    return 0


def cmd_check(args):
    """Только проверки: сборка без заливки, чтобы посмотреть находки."""
    proj = _project(args)
    site, data = _load(proj)
    summary = render.render_site(site, data, proj, faq=_faq(proj), artist_names=_artist_names(proj))
    _out({"checks": summary["checks"] or ["чисто"],
          "blocking": summary["blocking"]}, args)
    return 1 if summary["blocking"] else 0


def cmd_publish(args):
    proj = _project(args)
    site, data = _load(proj)
    summary = render.render_site(site, data, proj, faq=_faq(proj), artist_names=_artist_names(proj))
    # находки уровня «стоп» — это то, что уже один раз уехало на живой сайт
    # (кириллическая «В» в «Вonus», описание, обрезанное посреди имени)
    if summary["blocking"] and not args.ignore_checks:
        _out({"checks": summary["checks"],
              "status": "не залито: сначала почини найденное или --ignore-checks"}, args)
        return 1
    result = publish_mod.publish(proj, site, args.message, confirmed=args.confirm)
    _out({**result, "checks": summary["checks"]}, args)
    return 0


def _out(payload, args):
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return
    for key, value in payload.items():
        if isinstance(value, list):
            print(f"{key}:")
            for line in value:
                print(f"  {line}")
        else:
            print(f"{key}: {value}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сайт-портфолио музыканта")
    ap.add_argument("--project", default=".", help="папка проекта")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import", help="добавить из Spotify")
    imp.add_argument("url")
    imp.add_argument("--role", default="mix")
    imp.add_argument("--genre")
    imp.add_argument("--force-album", action="store_true")
    imp.set_defaults(func=cmd_import)

    sb = sub.add_parser("sandbox", help="собрать черновик для песочницы")
    sb.add_argument("--out")
    sb.add_argument("--state", help="файл с накопленными правками")
    sb.set_defaults(func=cmd_sandbox)

    apl = sub.add_parser("apply", help="перенести правки из песочницы в данные")
    apl.add_argument("state")
    apl.set_defaults(func=cmd_apply)

    rol = sub.add_parser("roles", help="проставить роли пачкой из файла")
    rol.add_argument("file")
    rol.set_defaults(func=cmd_roles)

    bld = sub.add_parser("build", help="собрать сайт")
    bld.set_defaults(func=cmd_build)

    chk = sub.add_parser("check", help="собрать и показать, что не так")
    chk.set_defaults(func=cmd_check)

    pub = sub.add_parser("publish", help="собрать и залить на GitHub")
    pub.add_argument("--message", default="Обновить сайт")
    pub.add_argument("--confirm", action="store_true")
    pub.add_argument("--ignore-checks", action="store_true",
                     help="залить, несмотря на находки уровня «стоп»")
    pub.set_defaults(func=cmd_publish)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
