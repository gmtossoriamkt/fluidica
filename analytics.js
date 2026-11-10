(function(){
  // Яндекс.Метрика и цели. Если REQUIRE_CONSENT = true, счётчик грузится только после согласия на cookie
  // (тот же ключ, что в cookie-consent.js); если false - грузится всегда.
  var REQUIRE_CONSENT = true;
  var COUNTER_ID = 114166129;
  var STORAGE_KEY = 'fluidica-cookie-consent';
  var CONSENT_EVENT = 'fluidica-consent';
  var loaded = false;

  function hasConsent(){
    try { return localStorage.getItem(STORAGE_KEY) === '1'; } catch (e) { return false; }
  }

  function load(){
    if (loaded) return;
    loaded = true;
    try {
      window.dataLayer = window.dataLayer || [];
      (function(m, e, t, r, i, k, a){
        m[i] = m[i] || function(){ (m[i].a = m[i].a || []).push(arguments); };
        m[i].l = 1 * new Date();
        for (var j = 0; j < document.scripts.length; j++) { if (document.scripts[j].src === r) { return; } }
        k = e.createElement(t); a = e.getElementsByTagName(t)[0]; k.async = 1; k.src = r;
        a.parentNode.insertBefore(k, a);
      })(window, document, 'script', 'https://mc.yandex.ru/metrika/tag.js?id=' + COUNTER_ID, 'ym');
      window.ym(COUNTER_ID, 'init', {
        ssr: true,
        webvisor: true,
        clickmap: true,
        ecommerce: 'dataLayer',
        referrer: document.referrer,
        url: location.href,
        accurateTrackBounce: true,
        trackLinks: true
      });
    } catch (e) {
      // Метрика недоступна или заблокирована - сайт работает без неё
    }
  }

  // Одна ссылка - одна цель: порядок проверок важен (MAX и «Позвонить» оба ведут на tel:)
  function goalFor(link){
    var href = link.getAttribute('href') || '';
    if (link.getAttribute('aria-label') === 'MAX') return 'click_max';
    if (href.indexOf('tel:') === 0) return 'click_phone';
    if (href.indexOf('mailto:') === 0) return 'click_email';
    if (href.indexOf('t.me/') !== -1) return 'click_telegram';
    if (/#contact$/.test(href)) return 'click_write_us';
    if (href.indexOf('/devices') === 0 || href.indexOf('/pumps/') === 0) return 'go_catalog';
    return null;
  }

  document.addEventListener('click', function(ev){
    try {
      if (!loaded || typeof window.ym !== 'function') return;
      var link = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
      if (!link) return;
      var goal = goalFor(link);
      if (goal) window.ym(COUNTER_ID, 'reachGoal', goal);
    } catch (e) {
      // цели не должны ломать клики по ссылкам
    }
  }, true);

  if (!REQUIRE_CONSENT || hasConsent()) {
    load();
  } else {
    window.addEventListener(CONSENT_EVENT, load, { once: true });
  }
})();
