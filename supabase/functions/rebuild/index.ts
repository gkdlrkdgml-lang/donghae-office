// 관리자 입력을 저장하면 바로 시장실 화면을 다시 만들게 GitHub 「매일 수집 · 화면 갱신」(mode=admin)을 실행.
// 승인된 관리자(admin·super)만, 1분에 한 번까지. GitHub 토큰(GH_DISPATCH_TOKEN)은 Supabase 비밀값에만 있음.
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const REPO = "gkdlrkdgml-lang/donghae-office";
let last = 0;
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" } });
}
async function roleOf(req: Request): Promise<string | null> {
  const auth = req.headers.get("authorization") || "", apikey = req.headers.get("apikey") || "", base = Deno.env.get("SUPABASE_URL") || "";
  if (!auth.startsWith("Bearer ") || !apikey || !base) return null;
  const h = { apikey, Authorization: auth };
  const u = await fetch(base + "/auth/v1/user", { headers: h });
  if (!u.ok) return null;
  const user = await u.json();
  const p = await fetch(base + "/rest/v1/profiles?select=role&id=eq." + user.id, { headers: h });
  if (!p.ok) return null;
  return (await p.json())?.[0]?.role ?? null;
}
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "POST만 됩니다" }, 405);
  const role = await roleOf(req);
  if (role !== "admin" && role !== "super") return json({ error: "승인된 관리자만 쓸 수 있습니다" }, 401);
  const tok = Deno.env.get("GH_DISPATCH_TOKEN") || "";
  if (!tok) return json({ error: "no_token" }, 503);
  if (Date.now() - last < 60_000) return json({ ok: true, queued: "이미 1분 안에 실행을 걸어 두었습니다" });
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/collect.yml/dispatches`, {
    method: "POST",
    headers: { Authorization: "Bearer " + tok, Accept: "application/vnd.github+json", "User-Agent": "donghae-office", "X-GitHub-Api-Version": "2022-11-28" },
    body: JSON.stringify({ ref: "main", inputs: { mode: "admin" } }),
  });
  if (r.status !== 204) return json({ error: "GitHub 실행 실패 " + r.status + " " + (await r.text()).slice(0, 200) }, 502);
  last = Date.now();
  return json({ ok: true });
});
