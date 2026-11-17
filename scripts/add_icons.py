#!/usr/bin/env python3
"""Подключает растровые иконки на всех страницах, где есть <link rel="icon" ... href="/favicon.svg">.

Сразу после строки с SVG-иконкой вставляются две строки:
  <link rel="icon" href="/favicon.ico" sizes="48x48">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
Исключения: components/consent-checkbox.html (заготовка, не страница) и yandex_*.html.

Новые страницы (build_pages.py берёт <head> у страницы-шаблона) получают теги автоматически.
Статьи блога приходят готовыми HTML-файлами - после их добавления запустите скрипт.

Скрипт идемпотентен: страницы, где оба тега уже есть, не трогаются. Переводы строк сохраняются.
Коды возврата: 0 - всё в порядке, 1 - есть ошибки или (с --check) есть страницы без тегов.
"""
import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules"}
SKIP_FILES = {"components/consent-checkbox.html"}
SVG_LINE = '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
ICO_LINE = '<link rel="icon" href="/favicon.ico" sizes="48x48">'
APPLE_LINE = '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
RE_SVG = re.compile(r"^" + re.escape(SVG_LINE) + r"(\r?\n)", re.M)


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
    parser = argparse.ArgumentParser(description="Подключение favicon.ico и apple-touch-icon на страницах сайта")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="корень репозитория (по умолчанию - родитель папки scripts)")
    parser.add_argument("--check", action="store_true",
                        help="ничего не писать; код 1, если где-то теги не подключены")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    added, present, errors = [], 0, []
    for path, rel in html_files(root):
        text = read_text(path)
        n_svg, n_ico, n_apple = (text.count(x) for x in (SVG_LINE, ICO_LINE, APPLE_LINE))
        if n_svg != 1:
            errors.append((rel, "строка с favicon.svg должна быть ровно одна (найдено %d)" % n_svg))
            continue
        if (n_ico, n_apple) == (1, 1):
            present += 1
            continue
        if (n_ico, n_apple) != (0, 0):
            errors.append((rel, "комплект тегов неполный или задублирован (ico: %d, apple-touch-icon: %d)" % (n_ico, n_apple)))
            continue
        if len(RE_SVG.findall(text)) != 1:
            errors.append((rel, "строка с favicon.svg должна стоять на отдельной строке"))
            continue
        new = RE_SVG.sub(lambda m: SVG_LINE + m.group(1) + ICO_LINE + m.group(1) + APPLE_LINE + m.group(1), text, count=1)
        added.append(rel)
        if not args.check:
            write_text(path, new)

    print("Уже подключено: %d, %s: %d" % (present, "нужно добавить" if args.check else "добавлено", len(added)))
    for rel, msg in errors:
        print("ОШИБКА %s: %s" % (rel, msg), file=sys.stderr)
    if errors or (args.check and added):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
