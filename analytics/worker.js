// AI Brief Analytics - Cloudflare Worker
// 轻量埋点采集：page_view / download_click / link_click
// 存储：Cloudflare KV

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // POST /track - 接收埋点事件
    if (request.method === 'POST' && url.pathname === '/track') {
      try {
        const event = await request.json();
        const { site, event: eventType, ts, url: pageUrl, path, page_date, visitor_id } = event;

        if (!site || !eventType) {
          return new Response(JSON.stringify({ error: 'missing site or event' }), {
            status: 400,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' }
          });
        }

        // 生成唯一 key
        const key = `${site}:${eventType}:${ts}:${Math.random().toString(36).slice(2, 8)}`;
        
        // 存储事件
        await env.ANALYTICS.put(key, JSON.stringify(event), {
          expirationTtl: 60 * 60 * 24 * 90 // 90 天过期
        });

        // 更新聚合计数（按日期）
        const dateKey = page_date || new Date(ts).toISOString().slice(0, 10).replace(/-/g, '');
        const counterKey = `${site}:counter:${dateKey}:${eventType}`;
        
        const current = await env.ANALYTICS.get(counterKey);
        const count = current ? parseInt(current) + 1 : 1;
        await env.ANALYTICS.put(counterKey, String(count), {
          expirationTtl: 60 * 60 * 24 * 365 // 1 年过期
        });

        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
    }

    // GET /stats - 查询统计数据（可选，需要 API_KEY）
    if (request.method === 'GET' && url.pathname === '/stats') {
      const authHeader = request.headers.get('Authorization');
      const apiKey = env.API_KEY;
      
      if (!apiKey || authHeader !== `Bearer ${apiKey}`) {
        return new Response(JSON.stringify({ error: 'unauthorized' }), {
          status: 401,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }

      const site = url.searchParams.get('site') || 'cmft-ai-brief';
      const date = url.searchParams.get('date'); // YYYYMMDD or YYYY-MM-DD
      
      try {
        let results = {};
        
        if (date) {
          // 查询特定日期
          const dateKey = date.replace(/-/g, '');
          const events = ['page_view', 'download_click', 'link_click'];
          
          for (const eventType of events) {
            const counterKey = `${site}:counter:${dateKey}:${eventType}`;
            const count = await env.ANALYTICS.get(counterKey);
            results[eventType] = count ? parseInt(count) : 0;
          }
        } else {
          // 查询最近 7 天汇总
          const today = new Date();
          const last7Days = [];
          for (let i = 6; i >= 0; i--) {
            const d = new Date(today);
            d.setDate(d.getDate() - i);
            last7Days.push(d.toISOString().slice(0, 10).replace(/-/g, ''));
          }
          
          for (const dateKey of last7Days) {
            results[dateKey] = {};
            const events = ['page_view', 'download_click', 'link_click'];
            for (const eventType of events) {
              const counterKey = `${site}:counter:${dateKey}:${eventType}`;
              const count = await env.ANALYTICS.get(counterKey);
              results[dateKey][eventType] = count ? parseInt(count) : 0;
            }
          }
        }

        return new Response(JSON.stringify({ site, results }), {
          status: 200,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        });
      }
    }

    // 404
    return new Response(JSON.stringify({ error: 'not found' }), {
      status: 404,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
};
