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
    "Wix Madefor Display": "400;700;800",
}
DEFAULT_WEIGHTS = "400;700"


def font_link(site):
    theme = site["theme"]
    families = list(dict.fromkeys([theme["font_head"], theme["font_body"]]))
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
    return (
        ":root{"
        f"--bg: {t['bg']};"
        f"--accent: {t['accent']};"
        f"--font-head: '{t['font_head']}', 'Arial Narrow', system-ui, sans-serif;"
        f"--font-body: '{t['font_body']}', system-ui, -apple-system, sans-serif;"
        "}")


def stylesheet(site):
    return css_variables(site) + (TEMPLATES / "site.css").read_text(encoding="utf-8")
