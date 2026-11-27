#!/usr/bin/env python3
"""Проверка блога и внутренних ссылок перед PR (только читает файлы, ничего не меняет).

Что проверяется:
  - JSON-LD парсится на всех страницах сайта;
  - битые внутренние ссылки (href/src, начинающиеся с «/») на всех страницах;
  - статьи blog/<slug>/: canonical и og:url = https://fluidica.ru/blog/<slug>/, есть Article и BreadcrumbList,
    title не длиннее 65 символов, description 110-160 символов, дата в шапке статьи = datePublished,
    dateModified не раньше datePublished, в «Читать дальше» не больше 8 ссылок,
    вопросы FAQPage (если есть) видны в тексте страницы;
  - blog/index.html: у каждой статьи есть карточка и наоборот, счётчик «N статей» с правильным
    склонением = число карточек, карточки по дате от новых к старым, дата карточки = дата статьи,
    у сетки .blog-grid нет data-reveal.

Коды возврата: 0 - ошибок нет, 1 - есть ошибки. Предупреждения на код не влияют.
"""
import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ORIGIN = "https://fluidica.ru"
SKIP_DIRS = {".git", "node_modules", ".claude", "factcheck"}
TITLE_MAX = 65
DESC_MIN, DESC_MAX = 110, 160
RELATED_MAX = 8
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]

RE_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
RE_LINK = re.compile(r'(?:href|src)="(/[^"]*)"')


def read(p):
    return p.read_text(encoding="utf-8")


def ru_date(s):
    """«18 ноября 2026» -> date, иначе None."""
    m = re.fullmatch(r"\s*(\d{1,2}) (\S+) (\d{4})\s*", s)
    if not m or m.group(2) not in MONTHS:
        return None
    return datetime.date(int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1)))


def plural_articles(n):
    if n % 10 == 1 and n % 100 != 11:
        return "статья"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "статьи"
    return "статей"


def graph_of(text):
    out = []
    for raw in RE_LD.findall(text):
        d = json.loads(raw)
        out.extend(d.get("@graph", [d]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Проверка блога и внутренних ссылок")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    errors, warnings = [], []

    pages = [p for p in sorted(root.rglob("*.html"))
             if not any(part in SKIP_DIRS for part in p.relative_to(root).parts)
             and not p.name.startswith("yandex_")]

    # 1. JSON-LD и битые ссылки по всему сайту
    links = 0
    for p in pages:
        rel = p.relative_to(root).as_posix()
        text = read(p)
        try:
            graph_of(text)
        except json.JSONDecodeError as e:
            errors.append("%s: JSON-LD не парсится (%s)" % (rel, e))
        for h in RE_LINK.findall(text):
            path = unquote(urlparse(h).path).lstrip("/")
            links += 1
            if path and not (root / path).is_file() and not (root / path / "index.html").is_file():
                errors.append("%s: битая ссылка %s" % (rel, h))

    # 2. Статьи блога
    articles = {}
    for p in sorted((root / "blog").glob("*/index.html")):
        slug = p.parent.name
        rel = p.relative_to(root).as_posix()
        text = read(p)
        url = "%s/blog/%s/" % (ORIGIN, slug)
        canon = re.search(r'''<link rel=["']canonical["'] href=["']([^"']+)["']''', text)
        ogurl = re.search(r'''<meta property=["']og:url["'] content=["']([^"']+)["']''', text)
        if not canon or canon.group(1) != url:
            errors.append("%s: canonical %s, нужно %s" % (rel, canon and canon.group(1), url))
        if not ogurl or ogurl.group(1) != url:
            errors.append("%s: og:url %s, нужно %s" % (rel, ogurl and ogurl.group(1), url))
        title = html.unescape(re.search(r"<title>(.*?)</title>", text, re.S).group(1))
        if len(title) > TITLE_MAX:
            errors.append("%s: title %d символов, нужно не больше %d" % (rel, len(title), TITLE_MAX))
        desc = re.search(r'''<meta name=["']description["'] content=["']([^"']*)["']''', text)
        dlen = len(html.unescape(desc.group(1))) if desc else 0
        if not DESC_MIN <= dlen <= DESC_MAX:
            warnings.append("%s: description %d символов (рекомендуется %d-%d)" % (rel, dlen, DESC_MIN, DESC_MAX))
        try:
            graph = graph_of(text)
        except json.JSONDecodeError:
            continue
        types = {g.get("@type") for g in graph}
        if "Article" not in types or "BreadcrumbList" not in types:
            errors.append("%s: в JSON-LD нужны Article и BreadcrumbList, есть %s" % (rel, sorted(types)))
        art = next((g for g in graph if g.get("@type") == "Article"), {})
        pub, mod = art.get("datePublished"), art.get("dateModified")
        if pub and mod and mod < pub:
            errors.append("%s: dateModified %s раньше datePublished %s" % (rel, mod, pub))
        meta = re.search(r'<div class="article-meta">\s*<span>([^<]+)</span>', text)
        shown = ru_date(meta.group(1)) if meta else None
        if pub and shown and shown.isoformat() != pub:
            errors.append("%s: дата в шапке %s, а datePublished %s" % (rel, shown, pub))
        rl = re.search(r'<div class="related-links">(.*?)</div>', text, re.S)
        if rl and rl.group(1).count("<a ") > RELATED_MAX:
            errors.append("%s: в «Читать дальше» %d ссылок, нужно не больше %d" % (rel, rl.group(1).count("<a "), RELATED_MAX))
        plain = html.unescape(re.sub(r"<[^>]+>", " ", text.split("</head>", 1)[-1]))
        plain = re.sub(r"\s+", " ", plain)
        for g in graph:
            if g.get("@type") == "FAQPage":
                for q in g.get("mainEntity", []):
                    name = re.sub(r"\s+", " ", q.get("name", "")).strip()
                    if name and name not in plain:
                        errors.append("%s: вопрос FAQPage не найден в тексте страницы: %s" % (rel, name[:70]))
        articles[slug] = shown

    # 3. Лента блога
    idx = root / "blog" / "index.html"
    text = read(idx)
    if re.search(r'<div class="blog-grid"[^>]*data-reveal', text):
        errors.append("blog/index.html: у .blog-grid не должно быть data-reveal")
    cards = re.findall(r'<a href="/blog/([^/"]+)/" class="blog-card">\s*<div class="blog-card-meta">\s*<span>([^<]+)</span>', text)
    card_slugs = [c[0] for c in cards]
    for slug in sorted(set(articles) - set(card_slugs)):
        errors.append("blog/index.html: нет карточки статьи %s" % slug)
    for slug in sorted(set(card_slugs) - set(articles)):
        errors.append("blog/index.html: карточка без статьи %s" % slug)
    dups = sorted({s for s in card_slugs if card_slugs.count(s) > 1})
    if dups:
        errors.append("blog/index.html: дубли карточек %s" % ", ".join(dups))
    m = re.search(r'<p class="section-desc">(\d+) (\S+) —', text)
    want = "%d %s" % (len(cards), plural_articles(len(cards)))
    if not m or "%s %s" % (m.group(1), m.group(2)) != want:
        errors.append("blog/index.html: счётчик «%s», нужно «%s»" % (m and "%s %s" % (m.group(1), m.group(2)), want))
    dates = [ru_date(d) for _, d in cards]
    for (slug, d), dt in zip(cards, dates):
        if dt is None:
            errors.append("blog/index.html: не разобрана дата карточки %s: %s" % (slug, d))
        elif articles.get(slug) and articles[slug] != dt:
            errors.append("blog/index.html: дата карточки %s (%s) не совпадает с датой статьи (%s)" % (slug, dt, articles[slug]))
    for i in range(1, len(dates)):
        if dates[i - 1] and dates[i] and dates[i] > dates[i - 1]:
            errors.append("blog/index.html: карточка %s новее предыдущей - порядок от новых к старым нарушен" % cards[i][0])

    print("Страниц: %d, внутренних ссылок: %d, статей блога: %d, карточек: %d" % (len(pages), links, len(articles), len(cards)))
    for w in warnings:
        print("Предупреждение: " + w)
    for e in errors:
        print("ОШИБКА: " + e)
    print("Ошибок: %d, предупреждений: %d" % (len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
