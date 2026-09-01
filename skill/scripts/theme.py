"""Тема: шрифты и цветовые переменные."""
from pathlib import Path
from urllib.parse import quote

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# Начертания, которые реально есть у шрифта. Просить несуществующее нельзя —
# Google Fonts отдаст ошибку и страница останется без шрифта.
FONT_WEIGHTS = {
    "Oswald": "500;700",
    "Golos Text": "400;500;700",
    "Onest": "400;500;800",
    "Unbounded": "400;700;900",
    "Manrope": "400;600;800",
    "Wix Madefor Display": "400;500;700",
    "Inter": "400;500;700",
}
DEFAULT_WEIGHTS = "400;700"


def _roles(site):
    """Головной/тело плюс необязательные лого и подпись — с падением на них,
    если в site.json свои шрифты для лого/подписи не заданы."""
    t = site["theme"]
    return {
        "head": t["font_head"],
        "body": t["font_body"],
        "brand": t.get("font_brand") or t["font_head"],
        "tagline": t.get("font_tagline") or t["font_body"],
        "util": t.get("font_util") or t["font_body"],
    }


def font_link(site):
    families = list(dict.fromkeys(_roles(site).values()))
    parts = "&".join(
        f"family={quote(name)}:wght@{FONT_WEIGHTS.get(name, DEFAULT_WEIGHTS)}"
        for name in families)
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{parts}'
        '&subset=cyrillic,cyrillic-ext,latin,latin-ext&display=swap">')


def css_variables(site):
    t = site["theme"]
    r = _roles(site)
    return (
        ":root{"
        f"--bg: {t['bg']};"
        f"--accent: {t['accent']};"
        f"--font-head: '{r['head']}', 'Arial Narrow', system-ui, sans-serif;"
        f"--font-body: '{r['body']}', system-ui, -apple-system, sans-serif;"
        f"--font-brand: '{r['brand']}', 'Arial Narrow', system-ui, sans-serif;"
        f"--font-tagline: '{r['tagline']}', system-ui, -apple-system, sans-serif;"
        f"--font-util: '{r['util']}', system-ui, -apple-system, sans-serif;"
        "}")


def stylesheet(site):
    return css_variables(site) + (TEMPLATES / "site.css").read_text(encoding="utf-8")
