#!/usr/bin/env python3
"""Добавляет в шапку сайта телефон и e-mail (рядом с кнопкой «Каталог»).

В каждой странице с блоком <div class="header-actions"> скрипт вставляет:
  - разметку: ссылки tel:+79853169104 и mailto:info@fluidica.ru;
  - стили (после правила .header-actions): на узких экранах e-mail скрывается,
    а телефон остаётся иконкой;
  - подключает /contact-copy.js: на компьютерах клик по tel:/mailto: копирует контакт
    в буфер обмена и показывает «Скопировано» (ссылка при этом работает как обычно).
Цели Метрики (click_phone, click_email) срабатывают автоматически через analytics.js.

Новые страницы (build_pages.py и др. берут шапку у страницы-шаблона) получают блок сами.
Статьи блога приходят готовыми HTML-файлами - после их добавления запустите скрипт.

Скрипт идемпотентен: страницы, где блок уже есть, не трогаются. Переводы строк не меняются.
Коды возврата: 0 - всё в порядке, 1 - есть ошибки или (с --check) есть страницы без блока.
"""
import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules"}
SKIP_FILES = {"components/consent-checkbox.html"}
MARK = "header-contact"
PHONE_HREF = "tel:+79853169104"
PHONE_TEXT = "+7 985 316-91-04"
MAIL = "info@fluidica.ru"

HTML_LINES = [
    '      <a href="mailto:%s" class="header-contact header-mail">%s</a>' % (MAIL, MAIL),
    '      <a href="%s" class="header-contact header-phone" aria-label="Позвонить: %s">'
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 '
    '19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 '
    '1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 '
    '1.7 2z"/></svg><span>%s</span></a>' % (PHONE_HREF, PHONE_TEXT, PHONE_TEXT),
]

CSS = """
  .header-contact{
    display:inline-flex;align-items:center;gap:7px;
    color:rgba(255,255,255,0.82);font-size:14px;font-weight:600;
    white-space:nowrap;transition:color .15s ease;
  }
  .header-contact:hover{color:var(--white);}
  .header-phone svg{flex-shrink:0;color:var(--accent);}
  @media (max-width:1100px){.header-mail{display:none;}}
  @media (max-width:560px){
    .header-actions{gap:14px;}
    .header-phone span{display:none;}
    .header-phone svg{width:20px;height:20px;}
  }"""

RE_ACTIONS_OPEN = re.compile(r'(<div class="header-actions">)(\r?\n)')
RE_ACTIONS_CSS = re.compile(r'(  \.header-actions\{[^}]*\})(\r?\n)')


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


SCRIPT_TAG = '<script src="/contact-copy.js" defer></script>'
ANALYTICS_TAG = '<script src="/analytics.js" defer></script>'


def add_script(text):
    """Подключает /contact-copy.js (копирование контактов по клику на компьютерах)."""
    if "contact-copy.js" in text:
        return text, False
    nl = "\r\n" if "\r\n" in text else "\n"
    if ANALYTICS_TAG in text:
        return text.replace(ANALYTICS_TAG, ANALYTICS_TAG + nl + SCRIPT_TAG, 1), True
    if "</body>" in text:
        return text.replace("</body>", SCRIPT_TAG + nl + "</body>", 1), True
    return text, False


def process(text):
    """Возвращает (новый_текст, статус): done / skip / noheader."""
    changed = False
    if MARK not in text:
        if not RE_ACTIONS_OPEN.search(text) or not RE_ACTIONS_CSS.search(text):
            return text, "noheader"
        nl = "\r\n" if "\r\n" in text else "\n"
        html = nl.join(HTML_LINES) + nl
        text = RE_ACTIONS_OPEN.sub(lambda m: m.group(1) + m.group(2) + html, text, count=1)
        css = CSS.replace("\n", nl)
        text = RE_ACTIONS_CSS.sub(lambda m: m.group(1) + css + m.group(2), text, count=1)
        changed = True
    text, added = add_script(text)
    if changed or added:
        return text, "done"
    return text, "skip"


def pages(root):
    for p in sorted(root.rglob("*.html")):
        rel = p.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in p.parts) or rel in SKIP_FILES:
            continue
        if p.name.startswith("yandex_"):
            continue
        yield p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="только проверить, ничего не менять")
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    done = skip = 0
    missing = []
    for p in pages(root):
        text = read_text(p)
        if "<header" not in text:
            continue
        new, status = process(text)
        rel = p.relative_to(root).as_posix()
        if status == "skip":
            skip += 1
        elif status == "noheader":
            missing.append(rel)
        else:
            done += 1
            if args.check:
                missing.append(rel)
            else:
                write_text(p, new)
    if args.check:
        print("Без блока контактов в шапке: %d" % len(missing))
        for m in missing:
            print("  " + m)
        return 1 if missing else 0
    print("Обновлено: %d, уже было: %d" % (done, skip))
    if missing:
        print("Не найден блок header-actions (проверьте вручную):")
        for m in missing:
            print("  " + m)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
