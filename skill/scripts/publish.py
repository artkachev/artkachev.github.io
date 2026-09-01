"""Заливка на GitHub. Сайт живёт в чужом репозитории, поэтому рамки жёсткие:
только тот репозиторий, что указан в site.json, и только свои файлы.
"""
import gzip
import json
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

MANAGED_PATHS = (
    "index.html", "track", "faq", "artist", "about", "covers", "assets", "sitemap.xml",
    "robots.txt", "llms.txt", "feed.xml", "lastmod.json", ".nojekyll", "CNAME", ".github/workflows/deploy.yml",
    ".github/workflows/fetch-covers.yml", "site.json", "data.json", "faq.json",
    "artist_genres.json", "artist_names.json", "about.json", "roles.txt", "skill",
    "CLAUDE.md",
    "README.md", ".gitignore",
    # файл-подтверждение Google Search Console — кладётся в корень руками,
    # сборщик его не создаёт и не трогает; см. CLAUDE.md → «Поисковые панели»
    "googlee22777088d24875d.html",
)

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


class PublishRefused(Exception):
    pass


def _git(proj, *args, check=True):
    return subprocess.run(["git", *args], cwd=str(proj), text=True,
                          capture_output=True, check=False if not check else False)


def _git_ok(proj, *args):
    res = _git(proj, *args)
    if res.returncode != 0:
        raise PublishRefused(
            f"git {' '.join(args)} не прошёл: {res.stderr.strip() or res.stdout.strip()}")
    return res


def _remote_slug(proj):
    res = _git(proj, "remote", "get-url", "origin")
    if res.returncode != 0 or not res.stdout.strip():
        raise PublishRefused("у проекта не задан удалённый репозиторий origin")
    url = res.stdout.strip().removesuffix(".git")
    if "github.com" not in url:
        raise PublishRefused(f"origin не на github.com: {url!r}")
    return url.split("github.com")[-1].lstrip(":/")


def guard_identity(proj):
    """Коммит подписывается настройками git, а не зашитым в скрипт человеком."""
    missing = [key for key in ("user.name", "user.email")
               if not _git(proj, "config", key).stdout.strip()]
    if missing:
        raise PublishRefused(
            "не задано " + " и ".join(missing) + ". Выполните один раз:\n"
            '  git config --global user.name "Артем Ткачев"\n'
            '  git config --global user.email "вашapochta@example.com"')


def guard(proj, site):
    """Заливать можно только в репозиторий из site.json."""
    slug = _remote_slug(proj)
    if slug != site["repo"]:
        raise PublishRefused(
            f"репозиторий проекта {slug!r} не совпадает с site.json {site['repo']!r}")
    return slug


def ensure_workflow(proj):
    """Кладём оба workflow: деплой и добор обложек с runner'ов GitHub."""
    written = []
    for name in ("deploy.yml", "fetch-covers.yml"):
        target = Path(proj) / ".github" / "workflows" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text((TEMPLATES / name).read_text(encoding="utf-8"),
                              encoding="utf-8")
        written.append(target)
    return written[0]


def fetch_covers_remotely(proj, site, timeout=300):
    """Из России Spotify CDN закрыт — обложки забирает workflow на GitHub."""
    res = subprocess.run(
        ["gh", "workflow", "run", "fetch-covers.yml", "--repo", site["repo"]],
        cwd=str(proj), text=True, capture_output=True)
    if res.returncode != 0:
        raise PublishRefused(
            f"не удалось запустить fetch-covers: {res.stderr.strip()}")
    subprocess.run(["gh", "run", "watch", "--repo", site["repo"], "--exit-status"],
                   cwd=str(proj), text=True, capture_output=True, timeout=timeout)
    _git_ok(proj, "pull", "--rebase", "origin", "main")
    return True


def changed_urls(proj, site):
    """Адреса страниц, которые уехали последним коммитом.

    Считать их по одной сборке нельзя: между публикациями сборка запускается
    много раз, и та, что идёт внутри publish, обычно не находит уже никаких
    отличий — всё изменилось раньше. Тогда список для переобхода выходил
    пустым, хотя страницы поменялись. Коммит же знает точно, что уехало.
    """
    res = _git(proj, "show", "--name-only", "--format=", "HEAD")
    urls = []
    for name in res.stdout.split():
        if name.endswith("index.html"):
            urls.append(f'{site["url"]}/{name[:-len("index.html")]}')
    return urls


def publish(proj, site, message, confirmed):
    proj = Path(proj)
    guard(proj, site)
    guard_identity(proj)
    if not confirmed:
        raise PublishRefused(
            "заливка в чужой репозиторий требует явного подтверждения (--confirm)")
    ensure_workflow(proj)
    _git_ok(proj, "fetch", "origin")
    managed = list(MANAGED_PATHS)
    # ключ IndexNow называется по самому ключу, в общий список его не впишешь
    if site.get("indexnow_key"):
        managed.append(f'{site["indexnow_key"]}.txt')
    present = [p for p in managed if (proj / p).exists()]
    if not present:
        raise PublishRefused("нечего заливать: файлы сайта не собраны")
    _git_ok(proj, "add", "--", *present)
    staged = _git(proj, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return {"status": "нечего публиковать", "paths": present}
    _git_ok(proj, "commit", "-m", message)
    # Ребейз только если реально отстали. Иначе git всё равно откажется —
    # в дереве почти всегда лежит что-то несохранённое (файл не из
    # MANAGED_PATHS, свежая сборка) — и пожалуется на unstaged changes,
    # а мы выдадим это за чужие изменения, которых нет.
    if _git(proj, "rev-parse", "--verify", "-q", "origin/main").returncode == 0:
        behind = _git(proj, "rev-list", "--count", "HEAD..origin/main").stdout.strip()
        if behind not in ("", "0"):
            res = _git(proj, "rebase", "origin/main")
            if res.returncode != 0:
                _git(proj, "rebase", "--abort")
                raise PublishRefused(
                    f"в репозитории есть чужие изменения ({behind} коммит(ов)), "
                    "которые не наложились автоматически. Коммит уже сделан — "
                    "разберите конфликт руками")
    _git_ok(proj, "push", "origin", "HEAD:main")
    return {"status": "залито", "files": len(staged.splitlines()), "paths": present,
            "urls": changed_urls(proj, site)}


INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def fetch(url, timeout=20):
    """Скачать страницу сайта: (код, тело).

    Через curl, если он есть, и только потом своими силами. Причина не в
    удобстве: с этой машины urllib читает с Pages ответы примерно до десяти
    килобайт, а на главной и на карте сайта повисает до таймаута — заголовки
    приходят, тело не идёт. curl договаривается с сервером по HTTP/2 и берёт
    те же адреса за треть секунды. Проверка выкладки, которая молча падает по
    таймауту, хуже отсутствующей: она сообщает «не выложено» про выложенное.
    """
    curl = shutil.which("curl")
    if curl:
        tmp = Path(tempfile.mkstemp(prefix="publish-fetch-")[1])
        try:
            res = subprocess.run(
                [curl, "-sS", "--compressed", "--max-time", str(timeout),
                 "-H", "Cache-Control: no-cache", "-o", str(tmp),
                 "-w", "%{http_code}", url],
                text=True, capture_output=True)
            if res.returncode != 0:
                raise OSError(f"curl: {res.stderr.strip() or res.returncode}")
            return int(res.stdout.strip() or 0), tmp.read_bytes()
        finally:
            tmp.unlink(missing_ok=True)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "*/*",
        "Accept-Encoding": "gzip", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return r.status, raw


def wait_live(proj, site, timeout=210, interval=7):
    """Ждём, пока Pages отдаст свежую сборку.

    IndexNow зовёт краулера сразу, а деплой идёт полминуты с лишним. Позвать
    на старую версию хуже, чем не звать: робот придёт, увидит прежнее и
    уйдёт. Сверяем живую карту сайта с только что собранной — совпали,
    значит выложено.
    """
    local = (Path(proj) / "sitemap.xml").read_text(encoding="utf-8")
    deadline = time.monotonic() + timeout
    while True:
        # к каждому опросу свой хвост в адресе: Pages отдают файл с
        # max-age=600, и первый же запрос до выкладки залипает в кеше CDN
        # на десять минут — без обхода мы всё это время сверяли бы старое
        url = f'{site["url"]}/sitemap.xml?ts={int(time.time())}'
        try:
            _, body = fetch(url, timeout=15)
            if body.decode("utf-8") == local:
                return True
        except OSError:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def ping_indexnow(site, urls, timeout=20):
    """Сказать Bing и Яндексу, какие адреса изменились.

    У Google открытого приёма нет — его Indexing API официально только для
    вакансий и трансляций, поэтому здесь только участники IndexNow. Ключ
    лежит файлом в корне сайта: сервис скачивает его и убеждается, что
    список присылает владелец.
    """
    key = site.get("indexnow_key")
    if not key:
        return "ключ не задан"
    urls = list(urls)[:10000]
    if not urls:
        return "нечего слать: изменившихся страниц нет"
    payload = json.dumps({
        "host": urlparse(site["url"]).netloc,
        "key": key,
        "keyLocation": f'{site["url"]}/{key}.txt',
        "urlList": urls,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        INDEXNOW_ENDPOINT, data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except OSError as e:
        return f"не отправлено: {e}"
    # 200 — принято, 202 — принято, ключ ещё проверяется
    ok = code in (200, 202)
    return f'{"отправлено" if ok else f"отказ {code}"}, адресов: {len(urls)}'


def verify_live(site, sample_cover=None, timeout=30):
    """Проверяем живой сайт, а не отчёт скрипта."""
    checks = {}
    targets = {"главная": f"{site['url']}/",
               "sitemap": f"{site['url']}/sitemap.xml"}
    if sample_cover:
        targets["обложка"] = f"{site['url']}/covers/{sample_cover}.jpg"
    for name, url in targets.items():
        try:
            checks[name] = fetch(url, timeout=timeout)[0]
        except Exception as exc:
            checks[name] = f"ошибка: {exc}"
    return checks
