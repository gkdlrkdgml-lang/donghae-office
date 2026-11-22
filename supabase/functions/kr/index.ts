// 국내 접속 중계: 해외(GitHub 서버)에서 막히는 정부 사이트를 서울 지역(ap-northeast-2)에서 대신 불러 줌.
// 수집기(서비스 키)만 쓸 수 있고, 허용한 주소(지방재정365)만 부름 — 아무 주소나 대신 부르는 중계가 되지 않게.
const ALLOW = [/^https:\/\/(www\.)?lofin365\.go\.kr\/lf\/hub\/[A-Z]+$/, /^https:\/\/(www\.)?lofin365\.go\.kr\/portal\/LF\d+\.do$/, /^https:\/\/(www\.)?lofin365\.go\.kr\/resources\/js\/[\w.-]+\.js$/,
  /^https:\/\/(www\.)?lofin365\.go\.kr\/lf\/pfinDtaOpen\/dtst\/dtstSvi\/retvDtstDts(Api|Sheet|Time)\.do$/];  // 데이터셋 안내(요청 주소·인자)  // 지방재정365 자료(hub)·공개 안내 화면(portal)만

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json; charset=utf-8" } });
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ error: "POST만 됩니다" }, 405);
  const svc = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  const auth = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  if (!svc || auth !== svc) return json({ error: "수집기 전용입니다" }, 401);
  let b: { url?: string; params?: Record<string, string>; post?: boolean } = {};
  try { b = await req.json(); } catch { /* 빈 본문 */ }
  const url = String(b.url || "");
  if (!ALLOW.some((r) => r.test(url))) return json({ error: "허용하지 않은 주소입니다" }, 400);
  const q = new URLSearchParams(b.params || {});
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 55000);
  try {
    const r = b.post
      ? await fetch(url, { method: "POST", body: q.toString(), signal: ctl.signal, headers: { "User-Agent": "donghae-office/1.0", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest" } })
      : await fetch(url + "?" + q.toString(), { signal: ctl.signal, headers: { "User-Agent": "donghae-office/1.0" } });
    const text = await r.text();
    return json({ status: r.status, text, region: Deno.env.get("SB_REGION") || "" });
  } catch (e) {
    return json({ error: "국내 접속도 실패: " + String(e) }, 502);
  } finally { clearTimeout(t); }
});
