/* Форма заявки на главной (блок #request).
 *
 * Куда уходит заявка - задаётся одной строкой ENDPOINT ниже (адрес облачной функции или
 * любого другого приёмника, который принимает JSON методом POST и отвечает {"ok": true}).
 * Пока ENDPOINT пустой, форма не теряет заявку: по кнопке открывается письмо на info@fluidica.ru
 * с уже заполненным текстом.
 * Задать адрес можно так: python3 scripts/add_request_form.py --endpoint https://.../
 */
(function () {
  'use strict';

  var ENDPOINT = 'https://functions.yandexcloud.net/d4e3trkm61o30ge721r0';
  var MAIL_TO = 'info@fluidica.ru';
  var MIN_FILL_MS = 2500; // быстрее человек форму не заполнит: защита от простых ботов

  var form = document.getElementById('request-form');
  if (!form) return;

  var consent = form.querySelector('#rf-consent');
  var submit = form.querySelector('#form-submit-button');
  var status = form.querySelector('.rf-status');
  var openedAt = Date.now();
  var sending = false;

  function sync() { submit.disabled = !consent.checked || sending; }
  consent.addEventListener('change', sync);
  sync();

  function setStatus(msg, kind) {
    status.textContent = msg || '';
    status.className = 'rf-status' + (kind ? ' is-' + kind : '');
  }

  function val(name) { return (form.elements[name].value || '').replace(/^\s+|\s+$/g, ''); }

  function validContact(v) {
    if (/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v)) return true;
    var digits = v.replace(/\D/g, '');
    return /^[+\d\s().-]+$/.test(v) && digits.length >= 10 && digits.length <= 15;
  }

  function mailtoHref(d) {
    var body = 'Имя и компания: ' + d.name + '\nТелефон или e-mail: ' + d.contact + '\nИзделие / задача: ' + d.task;
    return 'mailto:' + MAIL_TO + '?subject=' + encodeURIComponent('Заявка с сайта fluidica.ru') +
      '&body=' + encodeURIComponent(body);
  }

  function goal(name) {
    try { document.dispatchEvent(new CustomEvent('fluidica-goal', { detail: name })); } catch (e) { /* без цели */ }
  }

  function showThanks() {
    var card = form.parentNode;
    card.innerHTML = '<div class="rf-thanks" role="status"><h3>Заявка отправлена</h3>' +
      '<p>Спасибо! Мы свяжемся с вами по указанным контактам.</p></div>';
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    if (sending) return;
    var d = { name: val('name'), contact: val('contact'), task: val('task'), website: val('website') };

    if (d.name.length < 2) { setStatus('Укажите имя и компанию.', 'error'); form.elements.name.focus(); return; }
    if (!validContact(d.contact)) { setStatus('Укажите телефон (не меньше 10 цифр) или e-mail.', 'error'); form.elements.contact.focus(); return; }
    if (!consent.checked) { setStatus('Нужно согласие на обработку персональных данных.', 'error'); return; }

    if (!ENDPOINT) {
      goal('form_submit');
      setStatus('Откроется письмо с заполненным текстом: отправьте его из почтовой программы.', 'ok');
      window.location.href = mailtoHref(d);
      return;
    }

    sending = true; sync(); setStatus('Отправляем…');
    var payload = {
      name: d.name, contact: d.contact, task: d.task, website: d.website,
      t: Date.now() - openedAt, page: location.pathname, query: location.search.slice(0, 300)
    };
    var ctrl = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, 15000);

    // text/plain: не требует предварительного запроса CORS; приёмник разбирает тело как JSON
    fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: JSON.stringify(payload),
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok && j && j.ok }; }); })
      .then(function (res) {
        clearTimeout(timer);
        if (!res.ok) throw new Error('bad response');
        goal('form_submit');
        showThanks();
      })
      .catch(function () {
        clearTimeout(timer);
        sending = false; sync();
        status.className = 'rf-status is-error';
        status.innerHTML = 'Не получилось отправить. Напишите нам: <a href="' + mailtoHref(d).replace(/"/g, '&quot;') +
          '">открыть письмо</a> или позвоните +7 985 316-91-04.';
      });
  });
})();
