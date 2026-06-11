(() => {
  'use strict';
  const ENDPOINT = (window.AI_BRIEF_ANALYTICS_ENDPOINT ||
    document.querySelector('meta[name="ai-brief-analytics-endpoint"]')?.content || '').trim();
  const SITE = 'cmft-ai-brief';
  const now = () => new Date().toISOString();
  const anonId = () => {
    const key = 'ai_brief_aid';
    try {
      let v = localStorage.getItem(key);
      if (!v) {
        v = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + '-' + Math.random().toString(36).slice(2));
        localStorage.setItem(key, v);
      }
      return v;
    } catch (_) { return ''; }
  };
  const pageDate = () => {
    const m = location.pathname.match(/(20\d{6})(?:\.html)?$/);
    return m ? m[1] : '';
  };
  const classifyDownload = (href) => {
    const path = new URL(href, location.href).pathname.split('/').pop() || '';
    let type = 'file';
    const mDate = path.match(/(20\d{6})/);
    if (/7days\.pdf$/i.test(path)) type = 'weekly_pdf';
    else if (/latest\.pdf$/i.test(path) || /ai-brief-20\d{6}\.pdf$/i.test(path)) type = 'daily_pdf';
    else if (/overview.*\.png$/i.test(path)) type = 'overview_png';
    else if (/card.*\.png$/i.test(path)) type = 'card_png';
    return { file: path, file_type: type, file_date: mDate ? mDate[1] : '' };
  };
  const send = (event, data = {}) => {
    if (!ENDPOINT) return;
    const payload = JSON.stringify({
      site: SITE,
      event,
      ts: now(),
      url: location.href,
      path: location.pathname,
      referrer: document.referrer || '',
      title: document.title || '',
      page_date: pageDate(),
      visitor_id: anonId(),
      ua: navigator.userAgent || '',
      ...data
    });
    try {
      if (navigator.sendBeacon) {
        const ok = navigator.sendBeacon(ENDPOINT, new Blob([payload], { type: 'application/json' }));
        if (ok) return;
      }
      fetch(ENDPOINT, { method: 'POST', mode: 'cors', keepalive: true, headers: { 'content-type': 'application/json' }, body: payload }).catch(() => {});
    } catch (_) {}
  };
  const pageView = () => send('page_view');
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', pageView, { once: true });
  } else {
    pageView();
  }
  document.addEventListener('click', (ev) => {
    const a = ev.target.closest && ev.target.closest('a[href]');
    if (!a) return;
    const href = a.getAttribute('href') || '';
    const isDownload = a.hasAttribute('download') || /\.(pdf|png)(\?|#|$)/i.test(href);
    if (isDownload) {
      send('download_click', { ...classifyDownload(href), link_text: (a.textContent || '').trim().slice(0, 80) });
    } else {
      send('link_click', { link_url: new URL(href, location.href).href, link_text: (a.textContent || '').trim().slice(0, 80) });
    }
  }, true);
})();
