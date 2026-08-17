(function(){
  var STORAGE_KEY = 'fluidica-cookie-consent';
  if (localStorage.getItem(STORAGE_KEY) === '1') return;

  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var style = document.createElement('style');
  style.textContent =
    '#cookie-consent{position:fixed;left:0;right:0;bottom:0;z-index:200;' +
    'background:var(--primary,#0B3B4E);color:rgba(255,255,255,0.92);' +
    'padding:18px 24px;display:flex;flex-wrap:wrap;gap:14px 24px;align-items:center;justify-content:center;' +
    'border-top:1px solid rgba(255,255,255,0.12);font-family:var(--font-body,Inter,sans-serif);' +
    (reduceMotion ? '' : 'transition:transform .3s ease;') +
    '}' +
    '#cookie-consent.cookie-hidden{transform:translateY(100%);}' +
    '#cookie-consent p{margin:0;font-size:14px;line-height:1.5;max-width:640px;}' +
    '#cookie-consent a{color:var(--accent,#17B9C4);text-decoration:underline;}' +
    '#cookie-consent button{background:var(--accent,#17B9C4);color:var(--primary,#0B3B4E);border:none;' +
    'font-weight:700;font-size:14px;padding:11px 22px;border-radius:8px;cursor:pointer;white-space:nowrap;}' +
    '@media (max-width:560px){#cookie-consent{padding:16px;justify-content:flex-start;}}';
  document.head.appendChild(style);

  var banner = document.createElement('div');
  banner.id = 'cookie-consent';
  banner.setAttribute('role', 'dialog');
  banner.setAttribute('aria-live', 'polite');
  banner.innerHTML =
    '<p>Сайт использует файлы cookie для корректной работы. ' +
    '<a href="/privacy">Политика конфиденциальности</a>.</p>' +
    '<button type="button">Понятно</button>';

  function show(){
    document.body.appendChild(banner);
    banner.querySelector('button').addEventListener('click', function(){
      localStorage.setItem(STORAGE_KEY, '1');
      banner.classList.add('cookie-hidden');
      setTimeout(function(){ banner.remove(); }, reduceMotion ? 0 : 300);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', show);
  } else {
    show();
  }
})();
