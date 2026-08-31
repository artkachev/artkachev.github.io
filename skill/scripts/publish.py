"""Заливка на GitHub. Сайт живёт в чужом репозитории, поэтому рамки жёсткие:
только тот репозиторий, что указан в site.json, и только свои файлы.
"""
import subprocess
import urllib.request
from pathlib import Path

MANAGED_PATHS = (
    "index.html", "track", "faq", "covers", "assets", "sitemap.xml", "robots.txt",
    ".nojekyll", ".github/workflows/deploy.yml",
    ".github/workflows/fetch-covers.yml", "site.json", "data.json", "faq.json",
    "artist_genres.json", "roles.txt", "skill", "CLAUDE.md", "README.md",
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


def publish(proj, site, message, confirmed):
    proj = Path(proj)
    guard(proj, site)
    guard_identity(proj)
    if not confirmed:
        raise PublishRefused(
            "заливка в чужой репозиторий требует явного подтверждения (--confirm)")
    ensure_workflow(proj)
    _git_ok(proj, "fetch", "origin")
    if _git(proj, "rev-parse", "--verify", "-q", "origin/main").returncode == 0:
        res = _git(proj, "rebase", "origin/main")
        if res.returncode != 0:
            _git(proj, "rebase", "--abort")
            raise PublishRefused(
                "в репозитории есть чужие изменения, которые не наложились автоматически")
    present = [p for p in MANAGED_PATHS if (proj / p).exists()]
    if not present:
        raise PublishRefused("нечего заливать: файлы сайта не собраны")
    _git_ok(proj, "add", "--", *present)
    staged = _git(proj, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return {"status": "нечего публиковать", "paths": present}
    _git_ok(proj, "commit", "-m", message)
    _git_ok(proj, "push", "origin", "HEAD:main")
    return {"status": "залито", "files": len(staged.splitlines()), "paths": present}


def verify_live(site, sample_cover=None, timeout=30):
    """Проверяем живой сайт, а не отчёт скрипта."""
    checks = {}
    targets = {"главная": f"{site['url']}/",
               "sitemap": f"{site['url']}/sitemap.xml"}
    if sample_cover:
        targets["обложка"] = f"{site['url']}/covers/{sample_cover}.jpg"
    for name, url in targets.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                checks[name] = r.status
        except Exception as exc:
            checks[name] = f"ошибка: {exc}"
    return checks
