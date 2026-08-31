"""Проверки перед публикацией — то, что глаз пропускает, а поиск замечает.

Всё, что здесь ловится, однажды уже уехало на живой сайт: в названии трека
стояла кириллическая «В» в слове «Вonus», а описание FAQ обрывалось посреди
имени — «VERBEE, Kla». Такие мелочи выдают, что страницы собрали скриптом и
не прочитали глазами, поэтому сборка теперь проверяет их сама.

Проверяются данные и то, что сборщик из них сделал: заголовки и описания
страниц собираются по ходу рендера (см. render.head), готовый HTML обратно
не разбирается — источник истины остаётся в json.

Уровни: "стоп" — публиковать нельзя, "глянь" — на усмотрение человека.
"""
import re
import unicodedata

STOP, LOOK = "стоп", "глянь"

TITLE_MAX = 60          # дальше поиск обрезает заголовок
DESC_MIN, DESC_MAX = 70, 160

CYR = set("абвгдежзийклмнопрстуфхцчшщъыьэюяё")
LAT = set("abcdefghijklmnopqrstuvwxyz")

# слова, где смешение алфавитов — часть названия, а не опечатка
MIXED_OK = set()


def _words(text):
    return re.findall(r"[^\W\d_]+", text, re.UNICODE)


def _mixed(word):
    low = word.lower()
    return bool(set(low) & CYR) and bool(set(low) & LAT)


def _strings(node, path=""):
    """Все строки json с путём до каждой — чтобы находку можно было найти."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _strings(value, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def check_alphabets(sources):
    """Кириллица и латиница внутри одного слова — почти всегда опечатка.

    «Вonus» с кириллической «В» читается глазом как обычное слово, но в слаг
    уходит как «vonus», а поиск считает его отдельным словом.
    """
    out = []
    for name, data in sources.items():
        for path, text in _strings(data):
            for word in _words(text):
                if _mixed(word) and word not in MIXED_OK:
                    letters = ", ".join(
                        f"{ch} ({unicodedata.name(ch, '?')})"
                        for ch in dict.fromkeys(word) if ch.isalpha())
                    out.append((STOP, f"{name}{path}",
                                f"в слове «{word}» смешаны алфавиты: {letters}"))
    return out


def check_meta(pages):
    """Заголовок и описание каждой собранной страницы."""
    out = []
    for page in pages:
        where = page["url"]
        title, desc = page["title"], page["description"]
        if not title.strip():
            out.append((STOP, where, "пустой заголовок"))
        if not desc.strip():
            out.append((STOP, where, "пустое описание"))
            continue
        # обрыв на полуслове: последнее слово не закончено и не стоит многоточие
        if desc[-1].isalnum() and not desc.rstrip().endswith("…"):
            tail = desc.rsplit(" ", 1)[-1]
            if len(desc) >= DESC_MAX - 8:
                out.append((STOP, where,
                            f"описание обрывается на «…{tail}» — нет ни точки, "
                            f"ни многоточия"))
        if len(title) > TITLE_MAX:
            out.append((LOOK, where,
                        f"заголовок {len(title)} симв., поиск покажет ~{TITLE_MAX}"))
        if len(desc) > DESC_MAX:
            out.append((LOOK, where, f"описание {len(desc)} симв., длиннее {DESC_MAX}"))
        elif len(desc) < DESC_MIN:
            out.append((LOOK, where, f"описание {len(desc)} симв., короче {DESC_MIN}"))
    return out


def check_dashes(sources):
    """Дефисы, за которыми обычно прячется чужое форматирование.

    « - » между словами — это либо забытое тире, либо название с площадки
    вроде «Miss Cali (Hallelujah) - Imanbek Remix». Второе трогать нельзя,
    поэтому уровень «глянь», а не «стоп».
    """
    out = []
    for name, data in sources.items():
        for path, text in _strings(data):
            if "http" in text:
                continue
            if " - " in text:
                out.append((LOOK, f"{name}{path}",
                            f"« - » в «{text}» — тире или название с площадки?"))
            if "--" in text:
                out.append((LOOK, f"{name}{path}", f"двойной дефис в «{text}»"))
            if " – " in text:
                out.append((LOOK, f"{name}{path}",
                            f"короткое тире « – » в «{text}», обычно нужно «—»"))
    return out


def check_duplicates(data, pages):
    """Два раза один и тот же адрес или id — значит, работа задвоилась."""
    out = []
    seen = {}
    for page in pages:
        seen.setdefault(page["url"], 0)
        seen[page["url"]] += 1
    for url, count in seen.items():
        if count > 1:
            out.append((STOP, url, f"адрес собран {count} раза"))

    ids = {}
    for rel in data.get("releases") or []:
        for item in [rel] + list(rel.get("tracks") or []):
            key = item.get("id")
            if key:
                ids.setdefault(key, []).append(item.get("title", "?"))
    for key, titles in ids.items():
        if len(titles) > 1:
            out.append((STOP, f"data.json/{key}",
                        f"один id у разных треков: {', '.join(titles)}"))

    # считаем то, что становится работой на сайте: у альбома это его треки,
    # у сингла — сам релиз. Иначе альбом, названный по заглавному треку,
    # каждый раз выглядел бы дублем самого себя
    by_artist = {}
    for rel in data.get("releases") or []:
        items = list(rel.get("tracks") or []) or [rel]
        for item in items:
            if item.get("title"):
                pair = (item.get("artist") or rel.get("artist"), item["title"])
                by_artist[pair] = by_artist.get(pair, 0) + 1
    for (artist, title), count in by_artist.items():
        if count > 1:
            out.append((LOOK, "data.json",
                        f"«{title}» у {artist} встречается {count} раза"))
    return out


def check_stale(out_dir, slugs):
    """Папки, которых сборка больше не делает.

    Слаг меняется вместе с названием: починили «Вonus» → «Bonus», и адрес
    страницы стал другим. Старая папка при этом остаётся в репозитории и
    продолжает отдаваться поиску как отдельная страница с тем же текстом.
    Сборка её не трогает — что делать со старым адресом, решает человек:
    удалить или оставить заглушку с переадресацией.
    """
    track_dir = out_dir / "track"
    if not track_dir.is_dir():
        return []
    out = []
    for child in sorted(track_dir.iterdir()):
        if child.is_dir() and child.name not in slugs:
            page = child / "index.html"
            if page.is_file() and "http-equiv=\"refresh\"" in page.read_text(
                    encoding="utf-8", errors="ignore"):
                continue          # заглушка с переадресацией — так и задумано
            out.append((LOOK, f"track/{child.name}/",
                        "папка осталась от прежнего слага, сборка её больше "
                        "не делает — удалить или оставить переадресацию"))
    return out


#: не текст, а машинные поля: разбирать их на слова смысла нет
SKIP_KEYS = ("logo_svg", "analytics", "icons", "url", "featured")


def run(site, data, faq, pages, out_dir=None, slugs=()):
    """Все проверки разом. Возвращает список (уровень, где, что не так)."""
    clean_site = {k: v for k, v in site.items() if k not in SKIP_KEYS}
    sources = {"data.json": data, "site.json": clean_site}
    if faq:
        sources["faq.json"] = faq
    found = []
    found += check_alphabets(sources)
    found += check_meta(pages)
    found += check_dashes(sources)
    found += check_duplicates(data, pages)
    if out_dir is not None:
        found += check_stale(out_dir, set(slugs))
    return found


def report(found):
    """Строки для человека: сначала то, что блокирует."""
    order = {STOP: 0, LOOK: 1}
    return [f"[{level}] {where} — {what}"
            for level, where, what in sorted(found, key=lambda f: order[f[0]])]


def blocking(found):
    return [f for f in found if f[0] == STOP]
