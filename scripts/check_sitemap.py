#!/usr/bin/env python3
"""Сверяет sitemap.xml со страницами репозитория.

Страницей считается папка с index.html. Канонический URL: https://fluidica.ru/<путь>/
(для корня: https://fluidica.ru/). Исключаются служебные папки и страницы,
которые намеренно не входят в sitemap.

Коды возврата: 0 - всё совпадает, 1 - есть расхождения.
Флаг --fix дописывает недостающие URL (страницы блога - после последней записи блога,
остальные - в конец urlset), сохраняя существующие переводы строк.
"""
import argparse
import re
import sys
from pathlib import Path

ORIGIN = "https://fluidica.ru"
SKIP_TOP_DIRS = {"data", "scripts", "components", ".git", "node_modules"}
SERVICE_PAGES = {"oferta", "terms", "requisites", "privacy"}
LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")


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


def insert_missing(text, missing):
    """Возвращает text с дописанными URL, сохраняя переводы строк."""
    blog = sorted(u for u in missing if u.startswith(ORIGIN + "/blog/"))
    rest = sorted(u for u in missing if u not in blog)

    def entry(url):
        return "  <url><loc>" + url + "</loc></url>"

    if blog:
        line_re = re.compile(
            r"^[^\r\n]*<loc>" + re.escape(ORIGIN) + r"/blog/[^<]*</loc>[^\r\n]*(\r?\n)", re.M
        )
        matches = list(line_re.finditer(text))
        if matches:
            last = matches[-1]
            eol = last.group(1)
            ins = "".join(entry(u) + eol for u in blog)
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

    if missing or orphans or duplicates:
        return 1
    print("\nsitemap.xml совпадает со страницами.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
