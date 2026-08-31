"""Обложки лежат в репозитории: серверы Spotify недоступны из России.

Локальная качалка пробует напрямую, но при систематическом отказе сети
быстро сдаётся — дальше обложки забирает workflow fetch-covers.yml
с runner'ов GitHub, у которых доступ есть.
"""
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://i.scdn.co/image/"
SIZE = "ab67616d0000b273"  # 640 пикселей
TIMEOUT = 8
GIVE_UP_AFTER = 4  # столько отказов подряд = сеть закрыта, не ждём остальные


def cover_url(chash):
    return f"{BASE}{SIZE}{chash}"


def _fetch(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def write_ids(project_dir, hashes):
    """Список для workflow: по хешу в строке."""
    out = Path(project_dir) / "covers"
    out.mkdir(parents=True, exist_ok=True)
    ids = sorted({h for h in hashes if h})
    (out / "ids.txt").write_text("\n".join(ids) + "\n", encoding="utf-8")
    return len(ids)


def missing(project_dir, hashes):
    out = Path(project_dir) / "covers"
    return [h for h in dict.fromkeys(h for h in hashes if h)
            if not (out / f"{h}.jpg").exists()
            or (out / f"{h}.jpg").stat().st_size == 0]


def download(project_dir, hashes, fetcher=_fetch, give_up_after=GIVE_UP_AFTER):
    out = Path(project_dir) / "covers"
    out.mkdir(parents=True, exist_ok=True)
    result = {"saved": [], "skipped": [], "failed": [], "network_blocked": False}
    streak = 0
    for chash in dict.fromkeys(h for h in hashes if h):
        target = out / f"{chash}.jpg"
        if target.exists() and target.stat().st_size > 0:
            result["skipped"].append(chash)
            continue
        if result["network_blocked"]:
            result["failed"].append(chash)
            continue
        try:
            data = fetcher(cover_url(chash))
            if not data:
                raise OSError("пустой ответ")
            target.write_bytes(data)
            result["saved"].append(chash)
            streak = 0
        except Exception:
            result["failed"].append(chash)
            streak += 1
            if streak >= give_up_after and not result["saved"]:
                result["network_blocked"] = True
    write_ids(project_dir, hashes)
    return result
