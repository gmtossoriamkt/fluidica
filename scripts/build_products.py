#!/usr/bin/env python3
"""Собирает мета-описания и JSON-LD карточек товаров из data/products.json.

Для каждого товара из data/products.json правится product/<slug>/index.html:
  - <meta name="description"> и <meta property="og:description"> (а также
    <meta name="twitter:description">, если такой тег есть на странице);
  - блок <script type="application/ld+json"> (Product + BreadcrumbList).

Ничего не придумывается. Источники:
  - data/products.json: name, slug, category_slug, price (поле note - внутреннее, не используется);
  - сама страница карточки: текст .hero-sub, подпись и ссылка категории в хлебных крошках,
    видимая цена, фото из .hero-media (только если файл лежит рядом со страницей).

Описание: «<название> — <цена>. <предложение из текста страницы>», 110-160 символов.
Если одно предложение не подходит по длине, берутся два подряд; если и так не
подходит - первое предложение обрывается на границе оборота (запятая, двоеточие, тире),
при необходимости к нему добавляется следующее предложение целиком.

Скрипт идемпотентен: повторный запуск ничего не меняет. Переводы строк в файлах сохраняются.
Коды возврата: 0 - всё в порядке, 1 - есть ошибки или (с --check) страницы устарели.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

ORIGIN = "https://fluidica.ru"
DESC_MIN, DESC_MAX = 110, 160
LD_OPEN = '<script type="application/ld+json">'

RE_META_DESC = re.compile(r'(<meta name="description" content=")([^"]*)(">)')
RE_OG_DESC = re.compile(r'(<meta property="og:description" content=")([^"]*)(">)')
RE_TW_DESC = re.compile(r'(<meta name="twitter:description" content=")([^"]*)(">)')
RE_LD = re.compile(r'<script type="application/ld\+json">[\s\S]*?</script>')
RE_STYLE_END = re.compile(r"</style>(\r?\n)")
RE_H1 = re.compile(r"<h1[ >]")
RE_H1_TEXT = re.compile(r"<h1[^>]*>([^<]*)</h1>")
RE_HERO_SUB = re.compile(r'<p class="hero-sub">([^<]*)</p>')
RE_PRICE = re.compile(r'<span class="price-value">([^<]*)</span>')
RE_CRUMBS = re.compile(r'<nav class="breadcrumb"[^>]*>([\s\S]*?)</nav>')
RE_CRUMB_LINK = re.compile(r'<a href="([^"]+)"[^>]*>([^<]*)</a>')
RE_HERO_IMG = re.compile(r'<div class="hero-media">\s*<img src="\./([^"]+)"')
RE_CANONICAL = re.compile(r'<link rel="canonical" href="([^"]+)"')
RE_OG_URL = re.compile(r'<meta property="og:url" content="([^"]+)"')
RE_SENTENCES = re.compile(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z])")
RE_CLAUSE = re.compile(r"[,:]\s|\s—\s")


def read_text(path):
    # newline="" - не трогаем \r\n при чтении и записи
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def attr(text):
    """Экранирование для значения HTML-атрибута в двойных кавычках."""
    return (text.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def split_sentences(text):
    return [s.strip() for s in RE_SENTENCES.split(" ".join(text.split())) if s.strip()]


def clause_cuts(sentence):
    """Варианты первого предложения, оборванные на границе оборота, от длинного к короткому."""
    body = sentence.rstrip(".!? ")
    cuts = [body[: m.start()] for m in RE_CLAUSE.finditer(body)]
    return [c + "." for c in reversed(cuts) if c]


def build_description(name, price_text, sentences):
    """Возвращает (описание, способ). Способ нужен только для отчёта."""
    head = "%s — %s." % (name, price_text)
    fits = lambda s: DESC_MIN <= len(s) <= DESC_MAX
    for i, s in enumerate(sentences):
        cand = "%s %s" % (head, s)
        if fits(cand):
            return cand, "предложение %d" % (i + 1)
    for i in range(len(sentences) - 1):
        cand = "%s %s %s" % (head, sentences[i], sentences[i + 1])
        if fits(cand):
            return cand, "предложения %d+%d" % (i + 1, i + 2)
    for i, s in enumerate(sentences):
        for cut in clause_cuts(s):
            cand = "%s %s" % (head, cut)
            if fits(cand):
                return cand, "предложение %d, обрыв на обороте" % (i + 1)
    for i in range(len(sentences) - 1):
        for cut in reversed(clause_cuts(sentences[i])):
            cand = "%s %s %s" % (head, cut, sentences[i + 1])
            if fits(cand):
                return cand, "предложение %d, обрыв на обороте + предложение %d" % (i + 1, i + 2)
    return None, None


def ld_block(product, description, price, category_href, category_label, image_url, eol):
    page_url = "%s/product/%s/" % (ORIGIN, product["slug"])
    item = {"@type": "Product", "name": product["name"], "description": description, "url": page_url}
    if image_url:
        item["image"] = image_url
    if price is not None:
        item["offers"] = {"@type": "Offer", "price": price, "priceCurrency": "RUB"}
    crumbs = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": ORIGIN + "/"},
            {"@type": "ListItem", "position": 2, "name": category_label, "item": ORIGIN + category_href},
            {"@type": "ListItem", "position": 3, "name": product["name"], "item": page_url},
        ],
    }
    data = {"@context": "https://schema.org", "@graph": [item, crumbs]}
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return (LD_OPEN + "\n" + body + "\n</script>").replace("\n", eol)


def process(root, product):
    """Возвращает (новый текст страницы | None, исходный текст, описание, способ, ошибки)."""
    errors = []
    slug = product["slug"]
    page = root / "product" / slug / "index.html"
    if not page.is_file():
        return None, "", None, None, ["нет файла %s" % page]
    text = read_text(page)
    eol = "\r\n" if "\r\n" in text else "\n"

    sub = RE_HERO_SUB.search(text)
    price_m = RE_PRICE.search(text)
    crumbs_m = RE_CRUMBS.search(text)
    if not (sub and crumbs_m):
        return None, text, None, None, ["нет .hero-sub или хлебных крошек"]

    links = RE_CRUMB_LINK.findall(crumbs_m.group(1))
    if len(links) < 2:
        return None, text, None, None, ["в хлебных крошках меньше двух ссылок"]
    category_href, category_label = links[1][0], html.unescape(links[1][1])

    # согласованность страницы и данных
    if category_href != "/%s/" % product["category_slug"]:
        errors.append("категория в крошках %s != category_slug %s" % (category_href, product["category_slug"]))
    h1 = RE_H1_TEXT.search(text)
    if len(RE_H1.findall(text)) != 1 or not h1 or html.unescape(h1.group(1)) != product["name"]:
        errors.append("H1 не один или не совпадает с name")
    expected_url = "%s/product/%s/" % (ORIGIN, slug)
    for rx, label in ((RE_CANONICAL, "canonical"), (RE_OG_URL, "og:url")):
        m = rx.search(text)
        if not m or m.group(1) != expected_url:
            errors.append("%s не равен %s" % (label, expected_url))

    price = product.get("price")
    price_text = None
    if price is not None:
        if not price_m:
            errors.append("цена есть в данных, но нет на странице")
        else:
            price_text = html.unescape(price_m.group(1)).strip()
            if re.sub(r"\D", "", price_text) != str(price):
                errors.append("цена на странице %r != %s в данных" % (price_text, price))
    elif price_m:
        errors.append("цена есть на странице, но нет в данных")
    if errors:
        return None, text, None, None, errors

    sentences = split_sentences(html.unescape(sub.group(1)))
    if price_text:
        description, how = build_description(product["name"], price_text, sentences)
    else:
        # без публичной цены: название + предложение
        description, how = None, None
        for s in sentences:
            cand = "%s. %s" % (product["name"], s)
            if DESC_MIN <= len(cand) <= DESC_MAX:
                description, how = cand, "без цены"
                break
    if description is None:
        return None, text, None, None, ["не удалось уложить описание в %d-%d символов" % (DESC_MIN, DESC_MAX)]

    image_url = None
    img = RE_HERO_IMG.search(text)
    if img and (page.parent / img.group(1)).is_file():
        image_url = "%s/product/%s/%s" % (ORIGIN, slug, img.group(1))

    new = text
    for rx in (RE_META_DESC, RE_OG_DESC, RE_TW_DESC):
        found = rx.findall(new)
        if rx is RE_TW_DESC and not found:
            continue  # такого тега на странице нет - не добавляем
        if len(found) != 1:
            return None, text, None, None, ["тегов описания должно быть ровно 1, найдено %d" % len(found)]
        new = rx.sub(lambda m: m.group(1) + attr(description) + m.group(3), new)

    block = ld_block(product, description, price, category_href, category_label, image_url, eol)
    if RE_LD.search(new):
        new = RE_LD.sub(lambda m: block, new, count=1)
    else:
        m = RE_STYLE_END.search(new)
        if not m:
            return None, text, None, None, ["не найден </style>, некуда вставить JSON-LD"]
        new = new[: m.end()] + block + m.group(1) + new[m.end():]
    return new, text, description, how, []


def main(argv=None):
    parser = argparse.ArgumentParser(description="Мета-описания и JSON-LD карточек товаров из data/products.json")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="корень репозитория (по умолчанию - родитель папки scripts)")
    parser.add_argument("--check", action="store_true",
                        help="ничего не писать; код 1, если какая-то страница не соответствует данным")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    products = json.loads(read_text(root / "data" / "products.json"))

    changed, failed, descriptions = [], [], {}
    for product in products:
        new, old, description, how, errors = process(root, product)
        slug = product["slug"]
        if errors:
            failed.append((slug, errors))
            continue
        if description in descriptions:
            failed.append((slug, ["описание совпадает с %s" % descriptions[description]]))
            continue
        descriptions[description] = slug
        if new != old:
            changed.append(slug)
            if not args.check:
                write_text(root / "product" / slug / "index.html", new)
        print("%3d  %-45s %s" % (len(description), slug, how))

    print("\nТоваров в data/products.json: %d, уникальных описаний: %d" % (len(products), len(descriptions)))
    for slug, errors in failed:
        print("ОШИБКА %s: %s" % (slug, "; ".join(errors)), file=sys.stderr)
    if args.check:
        print("Страниц, которые нужно обновить: %d" % len(changed))
    else:
        print("Обновлено страниц: %d" % len(changed))
    if failed or (args.check and changed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
