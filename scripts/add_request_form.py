#!/usr/bin/env python3
"""Подключает собственную форму заявки на главной (блок #request).

Использование:
  python3 scripts/add_request_form.py                     # форма на сайте, письмо через mailto
  python3 scripts/add_request_form.py --endpoint https://functions.yandexcloud.net/XXXX
  python3 scripts/add_request_form.py --check             # только проверить

Что делает:
  1. index.html: в блок .final-cta («Расскажите, какая задача стоит перед лабораторией»)
     вставляет форму (поля «Имя и компания», «Телефон или e-mail», «Изделие / задача»,
     чекбокс согласия, кнопка «Отправить заявку» неактивна, пока нет согласия), стили и
     строку «Или свяжитесь напрямую». Кнопка «Написать нам» убирается: форма её заменяет.
     Подключает /request-form.js после analytics.js.
  2. Все страницы: кнопки «Оставить заявку» (href="/#contact" class="btn-primary")
     ведут на /#request, то есть к форме на главной.
  3. analytics.js: клики по /#request и data-scroll="request" считаются целью click_write_us,
     а событие fluidica-goal из формы - целью form_submit.
  4. С --endpoint: прописывает адрес приёмника заявок в request-form.js (строка ENDPOINT).
     Без него форма открывает письмо на info@fluidica.ru с заполненным текстом.

Скрипт идемпотентен: повторный запуск ничего не меняет. Переводы строк не меняются.
Коды возврата: 0 - всё в порядке, 1 - ошибка или (с --check) форма не подключена.
"""
import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules"}
ENDPOINT_RE = re.compile(r"^https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")
MARK = 'id="request-form"'

CSS = """
  .request-card{
    max-width:640px;margin:0 auto;background:var(--white);color:var(--ink);text-align:left;
    border-radius:14px;padding:32px;box-shadow:0 18px 48px rgba(0,0,0,0.22);
  }
  .rf-row{margin:0 0 18px;}
  .rf-row label{display:block;font-size:14px;font-weight:600;color:var(--primary);margin:0 0 6px;}
  .request-card input[type="text"],.request-card textarea{
    width:100%;font:inherit;font-size:16px;color:var(--ink);background:var(--white);
    border:1px solid var(--line);border-radius:8px;padding:12px 14px;
  }
  .request-card textarea{resize:vertical;min-height:110px;}
  .request-card input[type="text"]:focus,.request-card textarea:focus{
    outline:2px solid var(--accent);outline-offset:1px;border-color:var(--accent);
  }
  .rf-hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden;}
  .consent-row{display:flex;align-items:flex-start;gap:10px;margin:4px 0 22px;}
  .consent-row input[type="checkbox"]{flex:0 0 auto;width:18px;height:18px;margin-top:2px;accent-color:var(--accent);cursor:pointer;}
  .consent-row label{font-size:14px;line-height:1.5;color:var(--muted);cursor:pointer;}
  .consent-row a{color:var(--primary-2);text-decoration:underline;text-decoration-color:var(--line);text-underline-offset:2px;}
  .consent-row a:hover{color:var(--accent);}
  .rf-submit{width:100%;border:0;cursor:pointer;font:inherit;font-weight:700;}
  .rf-submit:disabled{opacity:.5;cursor:not-allowed;box-shadow:none;transform:none;}
  .rf-status{min-height:22px;margin:14px 0 0;font-size:14.5px;line-height:1.5;color:var(--muted);}
  .rf-status.is-error{color:#B3261E;}
  .rf-status.is-ok{color:var(--success);}
  .rf-status a{color:var(--primary-2);text-decoration:underline;}
  .rf-thanks{text-align:center;padding:24px 8px;}
  .rf-thanks h3{margin:0 0 10px;font-family:var(--font-display);font-size:24px;color:var(--primary);}
  .rf-thanks p{margin:0;color:var(--muted);font-size:16px;line-height:1.6;}
  .request-alt{margin:22px 0 0;font-size:15px;color:rgba(255,255,255,0.75);}
  .request-alt a{color:var(--white);font-weight:600;border-bottom:1px solid rgba(255,255,255,0.35);}
  .request-alt a:hover{border-bottom-color:var(--white);}
  .request-alt .sep{margin:0 10px;opacity:.5;}
  @media (max-width:560px){
    .request-card{padding:22px 18px;}
    .request-alt .sep{display:none;}
    .request-alt a{display:block;margin-top:8px;border-bottom:0;}
  }"""

BLOCK = """      <div class="request-card">
        <form class="request-form" id="request-form" novalidate>
          <div class="rf-row">
            <label for="rf-name">Имя и компания</label>
            <input type="text" id="rf-name" name="name" autocomplete="name" maxlength="120" required>
          </div>
          <div class="rf-row">
            <label for="rf-contact">Телефон или e-mail</label>
            <input type="text" id="rf-contact" name="contact" autocomplete="tel" maxlength="120" required>
          </div>
          <div class="rf-row">
            <label for="rf-task">Изделие / задача</label>
            <textarea id="rf-task" name="task" rows="4" maxlength="2000"></textarea>
          </div>
          <div class="rf-hp" aria-hidden="true"><label>Не заполняйте это поле <input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>
          <div class="consent-row">
            <input type="checkbox" id="rf-consent" name="consent">
            <label for="rf-consent">Даю <a href="/consent/" target="_blank" rel="noopener">согласие на обработку персональных данных</a>. С <a href="/privacy/" target="_blank" rel="noopener">политикой конфиденциальности</a> ознакомлен(а)</label>
          </div>
          <button type="submit" class="btn-primary rf-submit" id="form-submit-button" disabled>Отправить заявку</button>
          <p class="rf-status" role="status" aria-live="polite"></p>
        </form>
      </div>
      <p class="request-alt">Или свяжитесь напрямую: <a href="mailto:info@fluidica.ru">info@fluidica.ru</a><span class="sep">·</span><a href="tel:+79853169104">+7 985 316-91-04</a></p>
"""

SCRIPT_TAG = '<script src="/request-form.js" defer></script>'
ANALYTICS_TAG = '<script src="/analytics.js" defer></script>'


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def patch_index(text):
    """Возвращает (текст, статус): done / skip / error:<причина>."""
    if MARK in text:
        return text, "skip"
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r'(<section class="final-cta")(>)', text)
    actions = re.search(r'[ \t]*<div class="final-actions">.*?</div>\r?\n', text, re.S)
    css_anchor = re.search(r'(  \.final-actions\{[^}]*\})(\r?\n)', text)
    if not (m and actions and css_anchor and ANALYTICS_TAG in text):
        return text, "error:не найден блок .final-cta / .final-actions / analytics.js"
    block = BLOCK.replace("\n", nl)
    text = text[:actions.start()] + block + text[actions.end():]
    text = text.replace(m.group(0), m.group(1) + ' id="request"' + m.group(2), 1)
    css = CSS.replace("\n", nl)
    text = re.sub(r'(  \.final-actions\{[^}]*\})(\r?\n)',
                  lambda mm: mm.group(1) + css + mm.group(2), text, count=1)
    text = text.replace(ANALYTICS_TAG, ANALYTICS_TAG + nl + SCRIPT_TAG, 1)
    return text, "done"


def patch_cta_links(text):
    old = 'href="/#contact" class="btn-primary"'
    return text.replace(old, 'href="/#request" class="btn-primary"'), text.count(old)


GOAL_LISTENER = """
  // Событие из формы заявки (request-form.js): успешная отправка
  document.addEventListener('fluidica-goal', function(ev){
    try {
      if (loaded && typeof window.ym === 'function' && ev.detail) window.ym(COUNTER_ID, 'reachGoal', ev.detail);
    } catch (e) {
      // цели не должны ломать форму
    }
  });
"""


def patch_analytics(text):
    t = text
    t = t.replace("if (target === 'contact') return 'click_write_us';",
                  "if (target === 'contact' || target === 'request') return 'click_write_us';")
    t = t.replace("/#contact$/.test(href)", "/#(contact|request)$/.test(href)")
    if "fluidica-goal" not in t:
        nl = "\r\n" if "\r\n" in t else "\n"
        anchor = "  if (!REQUIRE_CONSENT || hasConsent()) {"
        if anchor in t:
            t = t.replace(anchor, GOAL_LISTENER.replace("\n", nl).lstrip("\r\n") + nl + anchor, 1)
    return t


def pages(root):
    for p in sorted(root.rglob("*.html")):
        rel = p.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in p.parts) or rel.startswith("components/"):
            continue
        if p.name.startswith("yandex_"):
            continue
        yield p


def set_endpoint(root, url):
    path = root / "request-form.js"
    t = read_text(path)
    new, n = re.subn(r"var ENDPOINT = '[^']*';", "var ENDPOINT = '%s';" % url, t, count=1)
    if n == 0:
        return "error:в request-form.js нет строки var ENDPOINT = '...';"
    if new == t:
        return "skip"
    write_text(path, new)
    return "done"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--endpoint", help="адрес приёмника заявок (https://...), прописывается в request-form.js")
    ap.add_argument("--check", action="store_true", help="только проверить, ничего не менять")
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    index = root / "index.html"

    if args.check:
        t = read_text(index)
        ok = MARK in t and "/request-form.js" in t and (root / "request-form.js").exists()
        left = sum(read_text(p).count('href="/#contact" class="btn-primary"') for p in pages(root))
        js = read_text(root / "request-form.js") if (root / "request-form.js").exists() else ""
        m = re.search(r"var ENDPOINT = '([^']*)';", js)
        ep = m.group(1) if m else ""
        print("Форма на главной: %s; кнопок на /#contact: %d; ENDPOINT: %s" %
              ("есть" if ok else "нет", left, ep or "не задан (письмо через mailto)"))
        return 0 if ok and left == 0 else 1

    if args.endpoint and not ENDPOINT_RE.match(args.endpoint):
        print("--endpoint должен быть адресом вида https://...")
        return 1
    if not (root / "request-form.js").exists():
        print("Нет файла request-form.js в корне сайта: положите его и запустите снова.")
        return 1

    text, status = patch_index(read_text(index))
    if status.startswith("error"):
        print("index.html: " + status)
        return 1
    if status != "skip":
        write_text(index, text)
    print("index.html: " + status)

    changed = 0
    for p in pages(root):
        t = read_text(p)
        new, n = patch_cta_links(t)
        if n:
            write_text(p, new)
            changed += 1
    print("Кнопок «Оставить заявку» переведено на /#request: страниц %d" % changed)

    an = root / "analytics.js"
    if an.exists():
        t = read_text(an)
        new = patch_analytics(t)
        if new != t:
            write_text(an, new)
            print("analytics.js: цели обновлены")
        else:
            print("analytics.js: без изменений")

    if args.endpoint:
        st = set_endpoint(root, args.endpoint)
        print("request-form.js ENDPOINT: " + st)
        if st.startswith("error"):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
