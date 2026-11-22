// 부지 검토용 중계: 시장실 사이트(또는 로그인한 관리자)에서만 건축물대장(건축HUB)을 필지번호(PNU)로 조회.
// 공공데이터포털 키(DATA_GO_KR_KEY)는 Supabase 비밀값에만 있고 브라우저로 나가지 않습니다.
// 건축HUB 호출 방식 참고: chrisryugj/archhub-mcp (MIT License)
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const HUB = "https://apis.data.go.kr/1613000/BldRgstHubService/";
const OPS: Record<string, string> = {
  recap: "getBrRecapTitleInfo",   // 총괄표제부
  title: "getBrTitleInfo",        // 표제부(동별)
  jijigu: "getBrJijiguInfo",      // 지역지구구역
  basis: "getBrBasisOulnInfo",    // 기본개요
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" } });
}

// 로그인 대신: 시장실 사이트에서 온 요청만 받고, 짧은 시간에 너무 많이 부르면 막음
const ALLOWED = ["https://gkdlrkdgml-lang.github.io"];
const hits = new Map<string, number[]>();
function tooMany(ip: string) {
  const now = Date.now(), win = 10 * 60 * 1000, max = 60;
  const arr = (hits.get(ip) || []).filter((t) => now - t < win);
  arr.push(now); hits.set(ip, arr);
  return arr.length > max;
}

async function whoIs(req: Request): Promise<string | null> {
  const auth = req.headers.get("authorization") || "";
  const apikey = req.headers.get("apikey") || "";
  const base = Deno.env.get("SUPABASE_URL") || "";
  if (!auth.startsWith("Bearer ") || !apikey || !base) return null;
  const h = { apikey, Authorization: auth };
  const u = await fetch(base + "/auth/v1/user", { headers: h });
  if (!u.ok) return null;
  const user = await u.json();
  const p = await fetch(base + "/rest/v1/profiles?select=role&id=eq." + user.id, { headers: h });
  if (!p.ok) return null;
  const rows = await p.json();
  return rows?.[0]?.role ?? null;
}

async function hub(op: string, prm: Record<string, string>, key: string) {
  const q = new URLSearchParams({ ...prm, serviceKey: key, _type: "json", numOfRows: "100", pageNo: "1" });
  const r = await fetch(HUB + op + "?" + q.toString());
  const t = await r.text();
  try {
    const j = JSON.parse(t);
    const head = j?.response?.header;
    if (head && head.resultCode !== "00") return { error: head.resultMsg || head.resultCode, items: [] };
    let it = j?.response?.body?.items?.item ?? [];
    if (!Array.isArray(it)) it = [it];
    return { items: it, total: Number(j?.response?.body?.totalCount || it.length) };
  } catch {
    return { error: t.slice(0, 200), items: [] };
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "POST만 됩니다" }, 405);
  const origin = req.headers.get("origin") || "";
  const ip = (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "?";
  // 로그인 잠금(2026-11-22): 승인된 계정(보기 전용·관리자·최고관리자)만
  const role = await whoIs(req);
  if (role !== "viewer" && role !== "admin" && role !== "super") return json({ error: "승인된 계정으로 로그인해야 합니다" }, 401);
  void origin; void ALLOWED;
  if (tooMany(ip)) return json({ error: "잠시 후 다시 시도해 주세요(10분에 60회까지)" }, 429);
  let body: { pnu?: string } = {};
  try { body = await req.json(); } catch { /* 빈 본문 */ }
  const pnu = String(body.pnu || "").trim();
  if (!/^\d{19}$/.test(pnu)) return json({ error: "PNU는 19자리 숫자여야 합니다" }, 400);
  const raw = Deno.env.get("DATA_GO_KR_KEY") || "";
  if (!raw) return json({ error: "DATA_GO_KR_KEY 비밀값이 없습니다" }, 500);
  const key = raw.includes("%") ? decodeURIComponent(raw) : raw;   // Encoding 키 → 원래 값
  const prm = {
    sigunguCd: pnu.slice(0, 5), bjdongCd: pnu.slice(5, 10),
    platGbCd: pnu[10] === "2" ? "1" : "0",          // PNU 11번째: 1 일반, 2 산
    bun: pnu.slice(11, 15), ji: pnu.slice(15, 19),
  };
  const out: Record<string, unknown> = { pnu, at: new Date().toISOString() };
  const res = await Promise.all(Object.entries(OPS).map(async ([k, op]) => [k, await hub(op, prm, key)] as const));
  for (const [k, v] of res) out[k] = v;
  return json(out);
});
