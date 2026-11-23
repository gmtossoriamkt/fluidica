#!/usr/bin/env python3
"""Сверяет sitemap.xml со страницами репозитория.

Страницей считается папка с index.html. Канонический URL: https://fluidica.ru/<путь>/
(для корня: https://fluidica.ru/). Исключаются служебные папки и страницы,
которые намеренно не входят в sitemap.

Коды возврата: 0 - всё совпадает, 1 - есть расхождения.
Флаг --fix дописывает недостающие URL (статьи блога - перед записью /blog/, а если её нет -
после последней статьи блога;
остальные - в конец urlset), сохраняя существующие переводы строк.
Флаг --lastmod проставляет каждой записи <lastmod>YYYY-MM-DD</lastmod> - дату последнего
git-коммита, менявшего index.html страницы (git log -1 --format=%cs). Если файл изменён,
но ещё не закоммичен, берётся сегодняшняя дата (она станет датой коммита).
Без --lastmod проверяется, что lastmod совпадает с этой датой (расхождения - код 1).
"""
import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

ORIGIN = "https://fluidica.ru"
SKIP_TOP_DIRS = {"data", "scripts", "components", ".git", "node_modules"}
SERVICE_PAGES = {"oferta", "terms", "requisites", "privacy"}
LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")
URL_RE = re.compile(r"<url>\s*<loc>\s*([^<]+?)\s*</loc>(?:\s*<lastmod>([^<]*)</lastmod>)?\s*</url>")


def read_text(path):
    # newline="" - не трогаем \r\n при чтении и записи
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def page_urls(root):
    """Канонические URL всех страниц, которые должны быть в sitemap."""
    urls = set()
    for index in root.rglob("index.html"):
        rel = index.parent.relative_to(root)
        parts = rel.parts
        if not parts:
            urls.add(ORIGIN + "/")
            continue
        if parts[0] in SKIP_TOP_DIRS or parts[0] in SERVICE_PAGES:
            continue
        if parts[0] == "blog" and len(parts) > 2:
            # глубже blog/<slug>/ - не статьи
            continue
        urls.add(ORIGIN + "/" + "/".join(parts) + "/")
    return urls


def sitemap_urls(sitemap_path):
    return LOC_RE.findall(read_text(sitemap_path))


def page_file(root, url):
    rel = url[len(ORIGIN):].strip("/")
    return (root / rel / "index.html") if rel else (root / "index.html")


def git_lastmod(root, path):
    """Дата последнего коммита, менявшего файл; сегодня - если есть незакоммиченные правки."""
    rel = path.relative_to(root).as_posix()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=root,
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        return datetime.date.today().isoformat()
    out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", rel], cwd=root,
                         capture_output=True, text=True, check=True).stdout.strip()
    return out or datetime.date.today().isoformat()


def lastmod_diffs(root, text):
    """[(url, в sitemap, ожидается)] для записей с отсутствующим или устаревшим lastmod."""
    diffs = []
    for m in URL_RE.finditer(text):
        url, current = m.group(1), m.group(2)
        path = page_file(root, url)
        if not path.is_file():
            continue
        expected = git_lastmod(root, path)
        if current != expected:
            diffs.append((url, current, expected))
    return diffs


def set_lastmod(root, text):
    def repl(m):
        path = page_file(root, m.group(1))
        if not path.is_file():
            return m.group(0)
        return "<url><loc>%s</loc><lastmod>%s</lastmod></url>" % (m.group(1), git_lastmod(root, path))
    return URL_RE.sub(repl, text)


def insert_missing(text, missing):
    """Возвращает text с дописанными URL, сохраняя переводы строк."""
    # сама лента /blog/ - после статей
    blog = sorted((u for u in missing if u.startswith(ORIGIN + "/blog/")),
                  key=lambda u: (u == ORIGIN + "/blog/", u))
    rest = sorted(u for u in missing if u not in blog)

    def entry(url):
        return "  <url><loc>" + url + "</loc></url>"

    if blog:
        # запись самой ленты /blog/ - статьи вставляются перед ней
        index_re = re.compile(
            r"^[^\r\n]*<loc>" + re.escape(ORIGIN) + r"/blog/</loc>[^\r\n]*(\r?\n)", re.M
        )
        # записи статей /blog/<slug>/ - запасной вариант: после последней из них
        article_re = re.compile(
            r"^[^\r\n]*<loc>" + re.escape(ORIGIN) + r"/blog/[^<]+</loc>[^\r\n]*(\r?\n)", re.M
        )
        index = index_re.search(text)
        articles = list(article_re.finditer(text))
        if index:
            ins = "".join(entry(u) + index.group(1) for u in blog)
            text = text[: index.start()] + ins + text[index.start():]
        elif articles:
            last = articles[-1]
            ins = "".join(entry(u) + last.group(1) for u in blog)
            text = text[: last.end()] + ins + text[last.end():]
        else:
            rest = sorted(set(rest) | set(blog))

    if rest:
        close = re.search(r"^[ \t]*</urlset>", text, re.M)
        if not close:
            raise SystemExit("В sitemap.xml не найден закрывающий </urlset>")
        eol = "\r\n" if "\r\n" in text else "\n"
        ins = "".join(entry(u) + eol for u in rest)
        text = text[: close.start()] + ins + text[close.start():]
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description="Сверка sitemap.xml со страницами сайта")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="корень репозитория (по умолчанию - родитель папки scripts)")
    parser.add_argument("--fix", action="store_true",
                        help="дописать недостающие URL в sitemap.xml")
    parser.add_argument("--lastmod", action="store_true",
                        help="проставить <lastmod> по дате последнего git-коммита страницы")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    sitemap_path = root / "sitemap.xml"
    if not sitemap_path.is_file():
        print("Не найден " + str(sitemap_path), file=sys.stderr)
        return 2

    pages = page_urls(root)
    listed = sitemap_urls(sitemap_path)
    listed_set = set(listed)

    missing = sorted(pages - listed_set)
    orphans = sorted(listed_set - pages)
    duplicates = sorted({u for u in listed if listed.count(u) > 1})

    print("Страниц на диске: %d, записей в sitemap: %d" % (len(pages), len(listed)))
    print("\nНет в sitemap (%d):" % len(missing))
    for u in missing:
        print("  " + u)
    print("\nЕсть в sitemap, но нет страницы (%d):" % len(orphans))
    for u in orphans:
        print("  " + u)
    if duplicates:
        print("\nДубликаты в sitemap (%d):" % len(duplicates))
        for u in duplicates:
            print("  " + u)

    if args.fix and missing:
        write_text(sitemap_path, insert_missing(read_text(sitemap_path), missing))
        print("\nДописано в sitemap.xml: %d" % len(missing))
        missing = []

    if args.lastmod:
        write_text(sitemap_path, set_lastmod(root, read_text(sitemap_path)))
    stale = lastmod_diffs(root, read_text(sitemap_path))
    print("\nlastmod не совпадает с датой git-коммита (%d):" % len(stale))
    for url, cur, exp in stale:
        print("  %s: %s -> %s" % (url, cur or "нет", exp))

    if missing or orphans or duplicates or stale:
        return 1
    print("\nsitemap.xml совпадает со страницами.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
