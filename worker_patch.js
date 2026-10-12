// x-unmei-bot (Cloudflare Worker) に足す公開ルート例（KVバインド名は既存に合わせる）
// 素材は @unmei_meiseki_ 用（@iching_kobo 側のWorker/KVには触れない）
//   GET  /today   -> { n, next, video_url, post1, post2 }
//   GET  /media   -> 当日のmp4本体（公開・キャッシュ可）
//   POST /advance -> cursor を +1（x-token ヘッダで保護）
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const n = Number(await env.UNMEI_KV.get("cursor")) || 0;

    if (url.pathname === "/media") {
      const body = await env.UNMEI_KV.get(`video:${n}`, "arrayBuffer");
      if (!body) return new Response("no media", { status: 404 });
      return new Response(body, { headers: { "content-type": "video/mp4", "cache-control": "public, max-age=86400" } });
    }
    if (url.pathname === "/today") {
      const meta = JSON.parse(await env.UNMEI_KV.get(`post:${n}`)); // {next, post1, post2}
      return Response.json({ n, next: meta.next, video_url: `${url.origin}/media`, post1: meta.post1, post2: meta.post2 });
    }
    if (url.pathname === "/advance" && req.method === "POST") {
      if (req.headers.get("x-token") !== env.ADVANCE_TOKEN) return new Response("forbidden", { status: 403 });
      await env.UNMEI_KV.put("cursor", String((n + 1) % 160));
      return Response.json({ ok: true, cursor: (n + 1) % 160 });
    }
    return new Response("not found", { status: 404 });
  },
};
