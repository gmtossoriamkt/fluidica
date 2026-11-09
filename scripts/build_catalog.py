#!/usr/bin/env python3
"""Собирает связки каталога из data/products.json и data/catalog_sections.json.

1. Страницы разделов насосов (/pumps/syringe/, /pumps/peristaltic/), см. data/catalog_sections.json:
   - если товары раздела определены по данным (правило name_contains), плейсхолдер
     «Товары скоро появятся» заменяется сеткой карточек в формате /devices/
     (.product-grid / .product-card), правится счётчик в .section-desc,
     описание страницы доводится до 110-160 символов;
   - если определить нельзя (правила нет), плейсхолдер остаётся, карточки не выдумываются;
   - в обоих случаях добавляется JSON-LD: BreadcrumbList (по видимым хлебным крошкам)
     и, если есть товары, ItemList.
2. Карточки товаров (product/<slug>/): блок «Смотрите также» - до 3 других товаров той же
   категории (category_slug), сначала из того же раздела насосов, дальше по кругу в порядке
   data/products.json. Блок вставляется перед .final-cta.

Скрипт идемпотентен, переводы строк в файлах сохраняются.
Коды возврата: 0 - всё в порядке, 1 - ошибки или (с --check) страницы устарели.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

ORIGIN = "https://fluidica.ru"
DESC_MIN, DESC_MAX = 110, 160
RELATED_COUNT = 3
LD_OPEN = '<script type="application/ld+json">'

RE_LD = re.compile(r'<script type="application/ld\+json">[\s\S]*?</script>')
RE_STYLE_END = re.compile(r"</style>(\r?\n)")
RE_META_DESC = re.compile(r'(<meta name="description" content=")([^"]*)(">)')
RE_OG_DESC = re.compile(r'(<meta property="og:description" content=")([^"]*)(">)')
RE_CRUMBS = re.compile(r'<nav class="breadcrumb"[^>]*>([\s\S]*?)</nav>')
RE_CRUMB_LINK = re.compile(r'<a href="([^"]+)"[^>]*>([^<]*)</a>')
RE_H1_TEXT = re.compile(r"<h1[^>]*>([^<]*)</h1>")
RE_GRID_BLOCK = re.compile(
    r'^      <div class="(?:placeholder-card|product-grid)" data-reveal>\r?\n[\s\S]*?^      </div>\r?\n', re.M)
RE_PLACEHOLDER_TEXT = re.compile(r'<p class="placeholder-text">([^<]*)</p>')
RE_SECTION_DESC = re.compile(r'(<section class="section" id="products">[\s\S]*?<p class="section-desc">)([^<]*)(</p>)')
RE_RELATED = re.compile(r'^  <section class="section" id="related">[\s\S]*?^  </section>\r?\n\r?\n', re.M)
RE_FINAL_CTA = re.compile(r'^  <section class="final-cta">', re.M)
RE_SENTENCES = re.compile(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z])")


def read_text(path):
    # newline="" - не трогаем \r\n при чтении и записи
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def attr(text):
    return (text.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def price_text(price):
    return "{:,}".format(price).replace(",", " ") + " ₽"


def plural_goods(n):
    a, b = n % 10, n % 100
    if a == 1 and b != 11:
        return "товар"
    if 2 <= a <= 4 and not 12 <= b <= 14:
        return "товара"
    return "товаров"


def crumbs_of(text):
    m = RE_CRUMBS.search(text)
    return [(href, html.unescape(label)) for href, label in RE_CRUMB_LINK.findall(m.group(1))] if m else []


def section_products(section, products):
    keyword = section.get("name_contains")
    if not keyword:
        return []
    return [p for p in products
            if p["category_slug"] == section["category_slug"] and keyword.lower() in p["name"].lower()]


def section_of(product, sections, products):
    for sec in sections:
        if product in section_products(sec, products):
            return sec["path"]
    return None


def card_html(product, indent, eol):
    pad = " " * indent
    lines = [
        '%s<a href="/product/%s/" class="product-card">' % (pad, product["slug"]),
        '%s  <span class="product-name">%s</span>' % (pad, attr(product["name"])),
        '%s  <span class="product-price">%s</span>' % (pad, price_text(product["price"])),
        '%s</a>' % pad,
    ]
    return eol.join(lines)


def grid_html(items, indent, eol):
    pad = " " * indent
    body = eol.join(card_html(p, indent + 2, eol) for p in items)
    return '%s<div class="product-grid" data-reveal>%s%s%s%s</div>%s' % (pad, eol, body, eol, pad, eol)


def ld_script(graph, eol):
    data = {"@context": "https://schema.org", "@graph": graph}
    return (LD_OPEN + "\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n</script>").replace("\n", eol)


def breadcrumb_ld(crumbs, page_url):
    items = []
    for i, (href, label) in enumerate(crumbs):
        url = page_url if i == len(crumbs) - 1 else (ORIGIN + href)
        items.append({"@type": "ListItem", "position": i + 1, "name": label, "item": url})
    return {"@type": "BreadcrumbList", "itemListElement": items}


def put_ld(text, block, eol):
    if RE_LD.search(text):
        return RE_LD.sub(lambda m: block, text, count=1)
    m = RE_STYLE_END.search(text)
    if not m:
        raise ValueError("не найден </style>, некуда вставить JSON-LD")
    return text[: m.end()] + block + m.group(1) + text[m.end():]


def css_chunks(root):
    """Стили сетки карточек берём из /devices/, чтобы вид совпадал один в один."""
    dev = read_text(root / "devices" / "index.html").replace("\r\n", "\n")
    grid = re.search(r"  \.product-grid\{[\s\S]*?(?=  \.grid-note\{)", dev)
    media = re.search(r"(  @media \(max-width:900px\)\{\n    \.product-grid[\s\S]*?\n  \}\n  @media \(max-width:560px\)\{\n    \.product-grid[\s\S]*?\n  \}\n)", dev)
    if not (grid and media):
        raise ValueError("не найдены стили .product-grid в devices/index.html")
    return grid.group(0), media.group(1)


def process_section_page(root, section, products, base_desc):
    path = root / section["path"] / "index.html"
    text = read_text(path)
    eol = "\r\n" if "\r\n" in text else "\n"
    url = "%s/%s/" % (ORIGIN, section["path"])
    items = section_products(section, products)
    crumbs = crumbs_of(text)
    h1 = html.unescape(RE_H1_TEXT.search(text).group(1))
    new = text
    graph = [breadcrumb_ld(crumbs, url)]

    if items:
        if not RE_GRID_BLOCK.search(new):
            raise ValueError("не найден плейсхолдер или сетка в #products")
        new = RE_GRID_BLOCK.sub(lambda m: grid_html(items, 6, eol), new, count=1)
        desc_text = "%d %s категории — цена и краткое описание на карточке." % (len(items), plural_goods(len(items)))
        new = RE_SECTION_DESC.sub(lambda m: m.group(1) + desc_text + m.group(3), new, count=1)
        if ".product-grid{" not in new:
            grid_css, media_css = css_chunks(root)
            anchor = "  .grid-note{"
            if new.count(anchor) != 1:
                raise ValueError("не найден .grid-note в стилях")
            new = new.replace(anchor, grid_css.replace("\n", eol) + anchor, 1)
            end_anchor = "  .grid-note a{color:var(--accent);text-decoration:underline;}" + eol
            if new.count(end_anchor) != 1:
                raise ValueError("не найден .grid-note a в стилях")
            new = new.replace(end_anchor, end_anchor + media_css.replace("\n", eol), 1)
        prices = sorted(p["price"] for p in items)
        if len(items) == 1:
            tail = " В каталоге 1 товар — %s." % price_text(prices[0])
        else:
            tail = " В каталоге %d %s — от %s до %s." % (
                len(items), plural_goods(len(items)), price_text(prices[0]), price_text(prices[-1]))
        description = base_desc + tail
        graph.append({
            "@type": "ItemList", "name": h1, "numberOfItems": len(items),
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": p["name"],
                 "url": "%s/product/%s/" % (ORIGIN, p["slug"])}
                for i, p in enumerate(items)],
        })
    else:
        # товары не определены: плейсхолдер остаётся, в описание берём его же второе предложение
        ph = RE_PLACEHOLDER_TEXT.search(new)
        if not ph:
            raise ValueError("нет ни товаров, ни плейсхолдера")
        sentences = [s for s in RE_SENTENCES.split(html.unescape(ph.group(1))) if s]
        description = "%s %s" % (base_desc, sentences[-1])

    if not DESC_MIN <= len(description) <= DESC_MAX:
        raise ValueError("описание %d символов, нужно %d-%d" % (len(description), DESC_MIN, DESC_MAX))
    for rx in (RE_META_DESC, RE_OG_DESC):
        if len(rx.findall(new)) != 1:
            raise ValueError("тегов описания должно быть ровно 1")
        new = rx.sub(lambda m: m.group(1) + attr(description) + m.group(3), new)
    new = put_ld(new, ld_script(graph, eol), eol)
    return path, text, new, "%d карточек, описание %d симв." % (len(items), len(description)) if items \
        else "плейсхолдер оставлен, описание %d симв." % len(description)


def related_for(product, products, sections):
    same_cat = [q for q in products if q["category_slug"] == product["category_slug"]]
    idx = {q["slug"]: i for i, q in enumerate(same_cat)}
    my_section = section_of(product, sections, products)

    def key(q):
        sec = section_of(q, sections, products)
        near = 0 if (my_section is not None and sec == my_section) else 1
        return (near, (idx[q["slug"]] - idx[product["slug"]]) % len(same_cat))

    return sorted((q for q in same_cat if q["slug"] != product["slug"]), key=key)[:RELATED_COUNT]


def process_product_page(root, product, products, sections):
    path = root / "product" / product["slug"] / "index.html"
    text = read_text(path)
    eol = "\r\n" if "\r\n" in text else "\n"
    crumbs = crumbs_of(text)
    if len(crumbs) < 2:
        raise ValueError("нет хлебных крошек")
    related = related_for(product, products, sections)
    if not related:
        return path, text, text, "нет связанных"
    block = eol.join([
        '  <section class="section" id="related">',
        '    <div class="wrap">',
        '      <div class="section-head" data-reveal>',
        '        <span class="section-label">%s</span>' % attr(crumbs[1][1]),
        '        <h2>Смотрите также</h2>',
        '      </div>',
        grid_html(related, 6, eol).rstrip("\r\n"),
        '    </div>',
        '  </section>',
    ]) + eol + eol
    new = text
    if RE_RELATED.search(new):
        new = RE_RELATED.sub(lambda m: block, new, count=1)
    else:
        m = RE_FINAL_CTA.search(new)
        if not m:
            raise ValueError("не найден .final-cta")
        new = new[: m.start()] + block + new[m.start():]
    return path, text, new, ", ".join(q["slug"] for q in related)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Разделы насосов и «Смотрите также» из data/*.json")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--check", action="store_true", help="ничего не писать; код 1, если страницы устарели")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    products = json.loads(read_text(root / "data" / "products.json"))
    sections = json.loads(read_text(root / "data" / "catalog_sections.json"))
    sitemap = {e["url"].strip("/"): e for e in json.loads(read_text(root / "data" / "sitemap.json"))}

    jobs, errors = [], []
    for sec in sections:
        base = sitemap[sec["path"]]["meta"]
        try:
            jobs.append(process_section_page(root, sec, products, base))
        except ValueError as e:
            errors.append((sec["path"], str(e)))
    for p in products:
        try:
            jobs.append(process_product_page(root, p, products, sections))
        except ValueError as e:
            errors.append((p["slug"], str(e)))

    changed = 0
    for path, old, new, info in jobs:
        rel = path.relative_to(root).as_posix()
        if rel.startswith("pumps/"):
            print("%-28s %s" % (rel, info))
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
