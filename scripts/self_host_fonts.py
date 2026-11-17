#!/usr/bin/env python3
"""Переводит страницы со шрифтов Google Fonts на собственный хостинг (/css/fonts.css, /fonts/*.woff2).

В <head> каждой страницы:
  - удаляются <link rel="preconnect"> на fonts.googleapis.com и fonts.gstatic.com
    и <link href="https://fonts.googleapis.com/css2?..." rel="stylesheet">;
  - на месте первой из удалённых строк вставляется блок:
      <link rel="preload" href="/fonts/inter-latin.woff2" as="font" type="font/woff2" crossorigin>
      <link rel="preload" href="/fonts/inter-cyrillic.woff2" as="font" type="font/woff2" crossorigin>
      <link rel="preload" href="/fonts/manrope-cyrillic.woff2" as="font" type="font/woff2" crossorigin>
      <link rel="stylesheet" href="/css/fonts.css">
Исключения: components/consent-checkbox.html (заготовка, не страница) и yandex_*.html.

build_pages.py берёт <head> у страницы-шаблона, поэтому новые страницы получают тот же блок.
Статьи блога приходят готовыми HTML-файлами - после их добавления запустите скрипт.

Скрипт идемпотентен: страницы, где блок уже стоит, не трогаются. Переводы строк сохраняются.
Коды возврата: 0 - всё в порядке, 1 - есть ошибки или (с --check) есть страницы, которые нужно обновить.
"""
import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules"}
SKIP_FILES = {"components/consent-checkbox.html"}
PRELOADS = ["inter-latin", "inter-cyrillic", "manrope-cyrillic"]
NEW_LINES = ['<link rel="preload" href="/fonts/%s.woff2" as="font" type="font/woff2" crossorigin>' % n
             for n in PRELOADS] + ['<link rel="stylesheet" href="/css/fonts.css">']
RE_OLD = re.compile(
    r'^<link rel="preconnect" href="https://fonts\.(?:googleapis|gstatic)\.com"(?: crossorigin)?>\r?\n'
    r'|^<link href="https://fonts\.googleapis\.com/css2\?[^"]*" rel="stylesheet">\r?\n', re.M)
RE_ANY_GOOGLE = re.compile(r"fonts\.(?:googleapis|gstatic)\.com")


def read_text(path):
    # newline="" - не трогаем \r\n при чтении и записи
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def html_files(root):
    for path in sorted(root.rglob("*.html")):
        rel = path.relative_to(root)
        if SKIP_DIRS & set(rel.parts):
            continue
        if rel.as_posix() in SKIP_FILES or rel.name.startswith("yandex_"):
            continue
        yield path, rel.as_posix()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Шрифты на собственном хостинге: правка <head> страниц")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="корень репозитория (по умолчанию - родитель папки scripts)")
    parser.add_argument("--check", action="store_true",
                        help="ничего не писать; код 1, если где-то нужно обновить <head>")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    for rel in ["css/fonts.css"] + ["fonts/%s.woff2" % n for n in PRELOADS]:
        if not (root / rel).is_file():
            print("ОШИБКА: нет файла %s" % rel, file=sys.stderr)
            return 1

    changed, present, errors = [], 0, []
    for path, rel in html_files(root):
        text = read_text(path)
        head_end = text.find("</head>")
        head = text[:head_end]
        if head_end < 0:
            errors.append((rel, "нет </head>"))
            continue
        olds = list(RE_OLD.finditer(head))
        n_css = head.count('<link rel="stylesheet" href="/css/fonts.css">')
        if not olds and n_css == 1 and not RE_ANY_GOOGLE.search(head) and all(
                head.count('href="/fonts/%s.woff2"' % n) == 1 for n in PRELOADS):
            present += 1
            continue
        if n_css or RE_ANY_GOOGLE.search(RE_OLD.sub("", head)) or len(olds) != 3:
            errors.append((rel, "неожиданный состав шрифтовых тегов (старых строк: %d, fonts.css: %d)" % (len(olds), n_css)))
            continue
        eol = "\r\n" if olds[0].group(0).endswith("\r\n") else "\n"
        block = eol.join(NEW_LINES) + eol
        out, pos = [], 0
        for i, m in enumerate(olds):
            out.append(head[pos:m.start()])
            if i == 0:
                out.append(block)
            pos = m.end()
        out.append(head[pos:])
        changed.append(rel)
        if not args.check:
            write_text(path, "".join(out) + text[head_end:])

    print("Уже переведено: %d, %s: %d" % (present, "нужно обновить" if args.check else "обновлено", len(changed)))
    for rel, msg in errors:
        print("ОШИБКА %s: %s" % (rel, msg), file=sys.stderr)
    if errors or (args.check and changed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
