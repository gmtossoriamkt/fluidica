/* Копирование контактов по клику на настольных компьютерах.
 * Ссылки tel: и mailto: остаются обычными (на телефонах открывают набор номера и почту).
 * На компьютере без почтовой программы или телефонного приложения клик ничего не показывал,
 * поэтому дополнительно копируем номер/адрес в буфер обмена и показываем подтверждение.
 * Переход по ссылке не отменяется. Только для устройств с мышью. */
(function () {
  'use strict';
  if (!window.matchMedia || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;

  var toast, timer;

  function show(msg) {
    if (!toast) {
      toast = document.createElement('div');
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      toast.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:100;' +
        'background:#0B3B4E;color:#fff;padding:11px 18px;border-radius:8px;font:500 14px/1.3 Inter,system-ui,sans-serif;' +
        'box-shadow:0 8px 24px rgba(11,59,78,.28);border:1px solid rgba(255,255,255,.12);opacity:0;' +
        'pointer-events:none;transition:opacity .15s ease;max-width:calc(100vw - 32px);';
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    clearTimeout(timer);
    timer = setTimeout(function () { toast.style.opacity = '0'; }, 2200);
  }

  function legacyCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;top:-100px;opacity:0;';
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }

  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return legacyCopy(text); });
    }
    return Promise.resolve(legacyCopy(text));
  }

  document.addEventListener('click', function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('a[href^="mailto:"], a[href^="tel:"]') : null;
    if (!a) return;
    var href = a.getAttribute('href');
    var raw = href.replace(/^(mailto:|tel:)/, '').split('?')[0];
    var text = href.indexOf('tel:') === 0 ? (a.textContent.trim() || raw) : raw;
    if (href.indexOf('tel:') === 0 && !/\d/.test(text)) text = raw;
    copy(text).then(function (ok) { if (ok) show('Скопировано: ' + text); });
  });
})();
