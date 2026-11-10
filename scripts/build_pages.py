#!/usr/bin/env python3
"""Собирает навигационные страницы из data/pages.json и data/sitemap.json.

Сейчас - /import-substitution/: подборка статей блога и ссылки на каталог.
Ничего не придумывается. Источники:
  - data/sitemap.json: H1 и meta страницы (meta-заглушка «...: подробная информация.»
    заменяется на вводный текст страницы, он укладывается в 110-160 символов);
  - data/pages.json: вводный абзац, подписи блоков, список статей и ссылок каталога;
  - blog/index.html: карточки статей копируются как есть (дата, чтение, тег, заголовок, описание);
  - заголовки страниц каталога (<h1> у /devices/, /pumps/... ) - подписи ссылок каталога.
Шапка, футер, стили и скрипты берутся из blog/index.html, стили карточек каталога - из devices/index.html,
поэтому страница остаётся в одном стиле с остальным сайтом. В JSON-LD: BreadcrumbList и CollectionPage.

Скрипт идемпотентен. Переводы строк берутся из blog/index.html.
Коды возврата: 0 - всё в порядке, 1 - ошибки или (с --check) страница устарела.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

ORIGIN = "https://fluidica.ru"
DESC_MIN, DESC_MAX = 110, 160
TITLE_MAX = 65
TITLE_SUFFIX = " - Fluidica"
TEMPLATE = "blog/index.html"
TEMPLATE_META_TAIL = "подробная информация."


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


def blog_cards(template):
    """slug -> (HTML карточки как в blog/index.html, заголовок)."""
    cards = {}
    for m in re.finditer(r'^        <a href="/blog/([^"/]+)/" class="blog-card">[\s\S]*?^        </a>\n', template, re.M):
        title = re.search(r'<h3 class="blog-card-title">([^<]*)</h3>', m.group(0)).group(1)
        cards[m.group(1)] = (m.group(0), html.unescape(title))
    return cards


def page_h1(root, url):
    text = read_text(root / url.strip("/") / "index.html")
    return html.unescape(re.search(r"<h1[^>]*>([^<]*)</h1>", text).group(1))


def product_css(root):
    """Стили сетки карточек - из /devices/, чтобы вид совпадал один в один."""
    dev = read_text(root / "devices" / "index.html").replace("\r\n", "\n")
    grid = re.search(r"  \.product-grid\{[\s\S]*?(?=  \.grid-note\{)", dev)
    media = re.search(r"(  @media \(max-width:900px\)\{\n    \.product-grid[\s\S]*?\n  \}\n  @media \(max-width:560px\)\{\n    \.product-grid[\s\S]*?\n  \}\n)", dev)
    if not (grid and media):
        raise ValueError("не найдены стили .product-grid в devices/index.html")
    return grid.group(0) + media.group(1)


def build_page(root, cfg, sitemap, template, cards):
    entry = sitemap[cfg["sitemap_url"]]
    h1 = entry["h1"]
    page_url = "%s/%s/" % (ORIGIN, cfg["path"])
    intro = cfg["intro"]

    meta = entry["meta"]
    description = intro if meta.endswith(TEMPLATE_META_TAIL) else meta
    if not DESC_MIN <= len(description) <= DESC_MAX:
        raise ValueError("описание %d символов, нужно %d-%d" % (len(description), DESC_MIN, DESC_MAX))
    title = cfg["title"] + TITLE_SUFFIX
    if len(title) > TITLE_MAX:
        raise ValueError("title %d символов, нужно не больше %d" % (len(title), TITLE_MAX))

    missing = [s for s in cfg["articles"] if s not in cards]
    if missing:
        raise ValueError("нет карточек в %s: %s" % (TEMPLATE, ", ".join(missing)))
    for url in cfg["catalog_links"]:
        if not (root / url.strip("/") / "index.html").is_file():
            raise ValueError("нет страницы каталога " + url)

    # ---- части шаблона: <head> до <style>, стили, шапка, футер со скриптами
    head_end = template.index("<style>")
    head = template[:head_end]
    style = template[head_end: template.index("</style>\n") + len("</style>\n")]
    body_start = template.index("<body>")
    header = template[body_start: template.index('<main id="top">')]
    footer = template[template.index("</main>"):]
    consent_line = '<script src="/cookie-consent.js" defer></script>\n'
    analytics_line = '<script src="/analytics.js" defer></script>\n'
    if consent_line in footer and analytics_line not in footer:
        # новые страницы не должны терять счётчик, даже если шаблон его ещё не содержит
        footer = footer.replace(consent_line, consent_line + analytics_line, 1)

    def sub1(rx, repl, text):
        out, n = re.subn(rx, lambda m: repl(m), text, count=1)
        if n != 1:
            raise ValueError("в шаблоне не найдено: " + rx)
        return out

    head = sub1(r"<title>[^<]*</title>", lambda m: "<title>%s</title>" % attr(title), head)
    head = sub1(r'<meta name="description" content="[^"]*">', lambda m: '<meta name="description" content="%s">' % attr(description), head)
    head = sub1(r'<link rel="canonical" href="[^"]*">', lambda m: '<link rel="canonical" href="%s">' % page_url, head)
    head = sub1(r'<meta property="og:title" content="[^"]*">', lambda m: '<meta property="og:title" content="%s">' % attr(title), head)
    head = sub1(r'<meta property="og:description" content="[^"]*">', lambda m: '<meta property="og:description" content="%s">' % attr(description), head)
    head = sub1(r'<meta property="og:url" content="[^"]*">', lambda m: '<meta property="og:url" content="%s">' % page_url, head)

    if ".product-grid{" not in style:
        anchor = "  .final-cta{"
        if style.count(anchor) != 1:
            raise ValueError("в стилях шаблона нет якоря .final-cta")
        style = style.replace(anchor, product_css(root) + "\n" + anchor, 1)

    graph = [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": ORIGIN + "/"},
            {"@type": "ListItem", "position": 2, "name": h1, "item": page_url}]},
        {"@type": "CollectionPage", "name": h1, "description": description, "url": page_url,
         "inLanguage": "ru",
         "mainEntity": {"@type": "ItemList", "numberOfItems": len(cfg["articles"]), "itemListElement": [
             {"@type": "ListItem", "position": i + 1, "name": cards[s][1], "url": "%s/blog/%s/" % (ORIGIN, s)}
             for i, s in enumerate(cfg["articles"])]}},
    ]
    ld = '<script type="application/ld+json">\n%s\n</script>\n' % json.dumps(
        {"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2)

    cards_html = "".join(cards[s][0] for s in cfg["articles"])
    catalog_html = "".join(
        '        <a href="%s" class="product-card">\n          <span class="product-name">%s</span>\n        </a>\n'
        % (url, attr(page_h1(root, url))) for url in cfg["catalog_links"])
    final_cta = re.search(r'  <section class="final-cta">[\s\S]*?  </section>\n', template).group(0)

    main = f'''<main id="top">

  <section class="hero">
    <div class="hero-inner">
      <nav class="breadcrumb" aria-label="Хлебные крошки">
        <a href="/">Главная</a><span>/</span>
        <a href="javascript:void(0)" data-scroll="top">{attr(h1)}</a>
      </nav>
      <span class="eyebrow">{attr(cfg["eyebrow"])}</span>
      <h1>{attr(h1)}</h1>
      <p class="hero-sub">{attr(intro)}</p>
    </div>
  </section>

  <section class="section" id="posts">
    <div class="wrap">
      <div class="section-head" data-reveal>
        <span class="section-label">{attr(cfg["articles_label"])}</span>
        <h2>{attr(cfg["articles_title"])}</h2>
        <p class="section-desc">{attr(cfg["articles_desc"])}</p>
      </div>
      <div class="blog-grid" data-reveal>
{cards_html}      </div>
    </div>
  </section>

  <section class="section section-surface" id="catalog">
    <div class="wrap">
      <div class="section-head" data-reveal>
        <span class="section-label">{attr(cfg["catalog_label"])}</span>
        <h2>{attr(cfg["catalog_title"])}</h2>
      </div>
      <div class="product-grid" data-reveal>
{catalog_html}      </div>
    </div>
  </section>

{final_cta}
'''
    return head + style + ld + "</head>\n" + header + main + footer


def main(argv=None):
    parser = argparse.ArgumentParser(description="Навигационные страницы из data/pages.json")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--check", action="store_true", help="ничего не писать; код 1, если страница устарела")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    raw_template = read_text(root / TEMPLATE)
    eol = "\r\n" if "\r\n" in raw_template else "\n"
    template = raw_template.replace("\r\n", "\n")
    pages = json.loads(read_text(root / "data" / "pages.json"))
    sitemap = {e["url"]: e for e in json.loads(read_text(root / "data" / "sitemap.json"))}
    cards = blog_cards(template)

    changed, errors = 0, []
    for cfg in pages:
        try:
            text = build_page(root, cfg, sitemap, template, cards).replace("\n", eol)
        except (ValueError, KeyError) as e:
            errors.append((cfg["path"], str(e)))
            continue
        target = root / cfg["path"] / "index.html"
        old = read_text(target) if target.is_file() else None
        print("%-26s %d симв. описание, %d статей" % (cfg["path"], len(re.search(r'name="description" content="([^"]*)"', text).group(1)), len(cfg["articles"])))
        if text != old:
            changed += 1
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                write_text(target, text)
    print("\n%s: %d" % ("Требуют обновления" if args.check else "Обновлено страниц", changed))
    for name, msg in errors:
        print("ОШИБКА %s: %s" % (name, msg), file=sys.stderr)
    return 1 if errors or (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
