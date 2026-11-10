#!/usr/bin/env python3
"""Подключает /analytics.js на всех страницах, где есть /cookie-consent.js.

Строка <script src="/analytics.js" defer></script> вставляется сразу после
<script src="/cookie-consent.js" defer></script>. Исключения: components/consent-checkbox.html
(заготовка, не страница) и файл подтверждения Яндекса yandex_*.html.

Скрипт идемпотентен: страницы, где analytics.js уже подключён, не трогаются.
Переводы строк каждого файла сохраняются.
Коды возврата: 0 - всё в порядке, 1 - есть ошибки или (с --check) есть страницы без подключения.
"""
import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules"}
SKIP_FILES = {"components/consent-checkbox.html"}
CONSENT_LINE = '<script src="/cookie-consent.js" defer></script>'
ANALYTICS_LINE = '<script src="/analytics.js" defer></script>'
RE_CONSENT = re.compile(r"^" + re.escape(CONSENT_LINE) + r"(\r?\n)", re.M)


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
    parser = argparse.ArgumentParser(description="Подключение analytics.js на страницах сайта")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="корень репозитория (по умолчанию - родитель папки scripts)")
    parser.add_argument("--check", action="store_true",
                        help="ничего не писать; код 1, если где-то analytics.js не подключён")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    added, present, errors = [], 0, []
    for path, rel in html_files(root):
        text = read_text(path)
        if CONSENT_LINE not in text:
            continue  # на странице нет баннера cookie - analytics.js не нужен
        count = text.count(ANALYTICS_LINE)
        if count == 1:
            present += 1
            continue
        if count > 1:
            errors.append((rel, "analytics.js подключён %d раза" % count))
            continue
        if len(RE_CONSENT.findall(text)) != 1:
            errors.append((rel, "строка cookie-consent.js должна быть ровно одна, на отдельной строке"))
            continue
        new = RE_CONSENT.sub(lambda m: CONSENT_LINE + m.group(1) + ANALYTICS_LINE + m.group(1), text, count=1)
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
