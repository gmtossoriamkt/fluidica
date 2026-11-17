#!/usr/bin/env python3
"""SEO служебных страниц и категорий из data/seo.json и data/products.json.

Для каждой записи data/seo.json с kind = "collection" или "webpage":
  - meta description и og:description заменяются на description из записи
    (шаблон {goods} - число товаров категории из data/products.json, например «3 товара»);
    description = null - текст страницы не трогаем, он только попадает в JSON-LD;
  - JSON-LD (@graph) собирается заново:
      collection - CollectionPage + BreadcrumbList (+ ItemList из товаров категории);
      webpage    - WebPage + BreadcrumbList.
    Названия в BreadcrumbList берутся из видимых хлебных крошек, name страницы - из H1.
    URL абсолютные (https://fluidica.ru/..., canonical-стиль, слэш на конце).
Записи kind = "catalog_section" (/pumps/...) обрабатывает build_catalog.py,
здесь они пропускаются; description для них тоже лежит в data/seo.json.

Title, H1 и видимый текст не меняются. Скрипт идемпотентен, переводы строк сохраняются.
Коды возврата: 0 - всё в порядке, 1 - ошибки или (с --check) страницы устарели.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_catalog import (  # noqa: E402
    ORIGIN, RE_META_DESC, RE_OG_DESC, RE_H1_TEXT, attr, breadcrumb_ld, crumbs_of,
    ld_script, plural_goods, put_ld, read_text, write_text)

DESC_MIN, DESC_MAX = 110, 160
RE_CARD_HREF = re.compile(r'<a href="/product/([^/"]+)/" class="product-card">')


def meta_description(text):
    m = RE_META_DESC.search(text)
    return html.unescape(m.group(2)) if m else ""


def process_page(root, entry, products):
    path = root / entry["path"] / "index.html"
    text = read_text(path)
    eol = "\r\n" if "\r\n" in text else "\n"
    url = "%s/%s/" % (ORIGIN, entry["path"])
    h1 = html.unescape(RE_H1_TEXT.search(text).group(1))
    crumbs = crumbs_of(text)
    if len(crumbs) < 2:
        raise ValueError("не найдены хлебные крошки")
    items = []
    if entry["kind"] == "collection":
        items = [p for p in products if p["category_slug"] == entry["category_slug"]]
        on_page = RE_CARD_HREF.findall(text)
        if sorted(on_page) != sorted(p["slug"] for p in items):
            raise ValueError("карточки на странице (%d) не совпадают с товарами категории в data/products.json (%d)"
                             % (len(on_page), len(items)))

    new = text
    if entry["description"] is None:
        description = meta_description(text)
    else:
        description = entry["description"]
        if "{goods}" in description:
            if not items:
                raise ValueError("в описании есть {goods}, а товаров в категории нет")
            description = description.replace("{goods}", "%d %s" % (len(items), plural_goods(len(items))))
        if not DESC_MIN <= len(description) <= DESC_MAX:
            raise ValueError("описание %d символов, нужно %d-%d" % (len(description), DESC_MIN, DESC_MAX))
        for rx in (RE_META_DESC, RE_OG_DESC):
            if len(rx.findall(new)) != 1:
                raise ValueError("тегов описания должно быть ровно 1")
            new = rx.sub(lambda m: m.group(1) + attr(description) + m.group(3), new)

    page = {"@type": "CollectionPage" if entry["kind"] == "collection" else "WebPage",
            "name": h1, "url": url, "description": description, "inLanguage": "ru"}
    graph = [page, breadcrumb_ld(crumbs, url)]
    if items:
        graph.append({
            "@type": "ItemList", "name": h1, "numberOfItems": len(items),
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": p["name"],
                 "url": "%s/product/%s/" % (ORIGIN, p["slug"])}
                for i, p in enumerate(items)],
        })
    new = put_ld(new, ld_script(graph, eol), eol)
    info = "%s, описание %d симв.%s%s" % (
        page["@type"], len(description), "" if entry["description"] is not None else " (не менялось)",
        ", ItemList %d" % len(items) if items else "")
    return path, text, new, info


def main(argv=None):
    parser = argparse.ArgumentParser(description="description и JSON-LD служебных страниц и категорий")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--check", action="store_true", help="ничего не писать; код 1, если страницы устарели")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    products = json.loads(read_text(root / "data" / "products.json"))
    entries = json.loads(read_text(root / "data" / "seo.json"))

    jobs, errors = [], []
    for entry in entries:
        if entry["kind"] == "catalog_section":
            continue
        try:
            jobs.append(process_page(root, entry, products))
        except ValueError as e:
            errors.append((entry["path"], str(e)))

    descs = {}
    for e in entries:
        if e["description"] is not None:
            descs.setdefault(e["description"], []).append(e["path"])
    for d, paths in descs.items():
        if len(paths) > 1:
            errors.append((", ".join(paths), "одинаковое описание"))

    changed = 0
    for path, old, new, info in jobs:
        rel = path.relative_to(root).as_posix()
        print("%-34s %s" % (rel, info))
        if new != old:
            changed += 1
            if not args.check:
                write_text(path, new)
    print("\nСтраниц обработано: %d, %s: %d" % (len(jobs), "требуют обновления" if args.check else "обновлено", changed))
    for name, msg in errors:
        print("ОШИБКА %s: %s" % (name, msg), file=sys.stderr)
    if errors or (args.check and changed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
