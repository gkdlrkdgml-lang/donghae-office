/* 동해시 AI 시장실 · 로그인 잠금(2026-11-22)
 * - 시장실 화면을 열면 먼저 로그인. 승인된 계정(보기 전용·관리자·최고관리자)만 자료를 받음.
 * - 자료(data.json.gz)는 Supabase 비공개 저장소(dash)에만 있고, 공개 사이트(GitHub Pages)에는 없음.
 * - 한 번 로그인하면 이 브라우저에 유지(TV는 처음 한 번만). 관리자 화면과 같은 로그인(dh_admin_auth).
 */
window.DHAuth = (function () {
  var C = window.DH_ADMIN || {};
  var DOMAINS = ['dh-office.local', 'dh-office.example.com'];
  var ROLE_OK = { viewer: 1, admin: 1, super: 1 };
  var sb = null;
  if (C.url && C.anonKey && window.supabase) {
    sb = window.supabase.createClient(C.url, C.anonKey, { auth: { persistSession: true, autoRefreshToken: true, storageKey: 'dh_admin_auth' } });
  }
  window.DH_SB = sb;

  function signIn(id, pw, i) {
    i = i || 0;
    return sb.auth.signInWithPassword({ email: id.toLowerCase() + '@' + DOMAINS[i], password: pw }).then(function (r) {
      if (r.error && i + 1 < DOMAINS.length && /Invalid login/i.test(r.error.message)) return signIn(id, pw, i + 1);
      if (r.error) throw r.error;
      return r;
    });
  }
  function profile() {
    return sb.auth.getSession().then(function (r) {
      var s = r.data.session;
      if (!s) return null;
      return sb.from('profiles').select('role,name').eq('id', s.user.id).maybeSingle().then(function (q) {
        if (q.error) throw q.error;
        return { session: s, profile: q.data || { role: 'pending' } };
      });
    });
  }

  // ---------- 로그인 화면 ----------
  var box = null;
  function overlay(msg, kind) {
    if (!box) {
      box = document.createElement('div');
      box.id = 'dhLogin';
      box.innerHTML =
        '<style>#dhLogin{position:fixed;inset:0;z-index:999;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#1B3A6B,#2F6DB5);font-family:"Pretendard","Malgun Gothic",system-ui,sans-serif}' +
        '#dhLogin .card{background:#fff;border-radius:18px;padding:34px 38px;width:min(440px,92vw);box-shadow:0 20px 60px rgba(0,0,0,.25)}' +
        '#dhLogin h1{margin:0 0 4px;font-size:26px;color:#1B3A6B}#dhLogin p{margin:0 0 20px;color:#556274;font-size:15px}' +
        '#dhLogin label{display:block;font-size:14px;font-weight:700;color:#38475A;margin:12px 0 4px}' +
        '#dhLogin input{width:100%;box-sizing:border-box;font:inherit;font-size:18px;padding:11px 13px;border:2px solid #C9D2DE;border-radius:10px}' +
        '#dhLogin button{margin-top:18px;width:100%;font:inherit;font-size:18px;font-weight:800;color:#fff;background:#1B3A6B;border:0;border-radius:10px;padding:12px;cursor:pointer}' +
        '#dhLogin .msg{min-height:22px;margin-top:12px;font-size:14px;font-weight:700}#dhLogin .msg.err{color:#D9534F}#dhLogin .msg.info{color:#1F6FD1}' +
        '#dhLogin .foot{margin-top:16px;font-size:13px;color:#6B7686}#dhLogin .foot a{color:#1F6FD1;font-weight:700}</style>' +
        '<form class="card" autocomplete="on"><h1>동해시 AI 시장실</h1><p>승인된 계정으로 로그인해 주세요.</p>' +
        '<label>아이디<input name="id" autocomplete="username" required></label>' +
        '<label>비밀번호<input name="pw" type="password" autocomplete="current-password" required></label>' +
        '<label style="display:flex;align-items:center;gap:8px;font-weight:700;margin-top:14px"><input type="checkbox" name="keep" checked style="width:20px;height:20px">이 기기에서 계속 로그인(로그인이 풀려도 자동으로 다시 로그인)</label>' +
        '<button type="submit">로그인</button><div class="msg"></div>' +
        '<div class="foot">처음이시면 <a href="admin.html">관리자 화면</a>에서 가입 신청 후 승인을 받으세요. 시장실 TV처럼 늘 켜 두는 기기는 「계속 로그인」을 켜 두세요. 여러 사람이 쓰는 PC에서는 끄세요.<br><a href="#" id="dhInstLink">⤓ 이 기기 바탕화면(홈 화면)에 앱으로 설치</a></div></form>';
      document.body.appendChild(box);
      var il = box.querySelector('#dhInstLink');
      if (il) { if (window.DHInstall && !DHInstall.installed()) { il.style.display = DHInstall.ready() ? '' : 'none'; window.addEventListener('beforeinstallprompt', function () { setTimeout(function () { il.style.display = ''; }, 0); }); } if (window.DHInstall && !DHInstall.installed()) il.onclick = function (e) { e.preventDefault(); DHInstall.open(); }; else il.remove(); }
    }
    var m = box.querySelector('.msg');
    m.className = 'msg ' + (kind || '');
    m.textContent = msg || '';
    return box;
  }
  function hide() { if (box) { box.remove(); box = null; } }

  // ---------- 로그인 유지 ----------
  // 30분마다 화면을 새로 고칠 때 인터넷이 잠깐 끊기거나 토큰 갱신이 꼬여도 로그인 화면으로 떨어지지 않게:
  //  ① 잠깐 실패하면 몇 번 다시 시도  ② 그래도 안 되면 이 기기에 저장한 승인 정보로 화면을 열고 다음에 다시 확인
  //  ③ 세션이 정말 사라졌으면 「이 기기에서 계속 로그인」으로 저장한 아이디·비밀번호로 조용히 다시 로그인
  var RK = 'dh_auth_role', AK = 'dh_auth_keep';
  function lsGet(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } }
  function lsSet(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function enc(t) { try { return btoa(unescape(encodeURIComponent(t))).split('').reverse().join(''); } catch (e) { return ''; } }
  function dec(t) { try { return decodeURIComponent(escape(atob(String(t).split('').reverse().join('')))); } catch (e) { return ''; } }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function profileRetry(n) {   // 네트워크 오류면 다시 시도, 세션 없음(null)은 바로 돌려줌
    return profile().catch(function (e) {
      if (n <= 0) throw e;
      return wait(n >= 3 ? 1500 : n === 2 ? 4000 : 9000).then(function () { return profileRetry(n - 1); });
    });
  }
  function silentLogin() {
    var k = lsGet(AK);
    if (!k || !k.id || !k.pw) return Promise.resolve(null);
    return signIn(k.id, dec(k.pw)).then(function () { return profileRetry(2); }).catch(function (e) {
      if (/Invalid login/i.test((e && e.message) || '')) lsSet(AK, null);   // 비밀번호가 바뀐 경우만 지움
      return null;
    });
  }
  function ok(p) { if (p && ROLE_OK[p.profile.role]) { lsSet(RK, { role: p.profile.role, uid: p.session.user.id, at: Date.now() }); return true; } return false; }

  // 승인된 계정이 로그인할 때까지 기다림
  function gate() {
    if (!sb) return Promise.reject(new Error('로그인 설정(admin-config.js)이 없습니다'));
    return profileRetry(3).then(function (p) {
      if (ok(p)) return p;
      if (p) return p;                    // 승인 안 됨·중지 → 아래에서 안내
      return silentLogin().then(function (q) { return ok(q) ? q : (q || null); });
    }, function () {
      // 계속 연결이 안 됨: 이 기기에서 승인된 적이 있으면 마지막 자료로 일단 화면을 엶
      var c = lsGet(RK);
      if (c && ROLE_OK[c.role]) return { session: null, profile: { role: c.role }, offline: true };
      return null;
    }).then(function (p) {
      if (p && ROLE_OK[p.profile.role]) return p;
      return new Promise(function (resolve) {
        var b = overlay(p ? (p.profile.role === 'off' ? '사용이 중지된 계정입니다.' : '아직 승인되지 않은 계정입니다. 최고관리자의 승인을 기다려 주세요.') : '', p ? 'err' : '');
        var f = b.querySelector('form');
        f.onsubmit = function (e) {
          e.preventDefault();
          var id = f.id.value.trim(), pw = f.pw.value, keep = f.keep ? f.keep.checked : true;
          overlay('로그인 중…', 'info');
          signIn(id, pw).then(function () { return profileRetry(2); }).then(function (q) {
            if (ok(q)) { lsSet(AK, keep ? { id: id, pw: enc(pw) } : null); hide(); resolve(q); }
            else overlay(q && q.profile.role === 'off' ? '사용이 중지된 계정입니다.' : '아직 승인되지 않은 계정입니다. 최고관리자의 승인을 기다려 주세요.', 'err');
          }).catch(function (err) {
            var t = (err && err.message) || String(err);
            overlay(/Invalid login/i.test(t) ? '아이디 또는 비밀번호가 맞지 않습니다.' : /fetch|network|Failed/i.test(t) ? '인터넷 연결을 확인해 주세요.' : t, 'err');
          });
        };
        setTimeout(function () { try { f.id.focus(); } catch (e) {} }, 50);
      });
    });
  }

  // ---------- 자료 받기(압축 풀기) · 인터넷이 잠깐 끊기면 이 기기에 마지막으로 받은 자료 사용 ----------
  var CK = 'dh-data-v1', CKEY = '/__dh_data__';
  function gunzip(blob) {
    if (!window.DecompressionStream) return Promise.reject(new Error('이 브라우저는 자료 압축 풀기를 지원하지 않습니다(최신 Chrome·Edge를 써 주세요)'));
    return new Response(blob.stream().pipeThrough(new DecompressionStream('gzip'))).text();
  }
  function download() {
    return sb.storage.from('dash').download('data/data.json.gz?t=' + Date.now()).then(function (r) {
      if (r.error) throw r.error;
      return gunzip(r.data);
    });
  }
  function loadData() {
    return download().catch(function (e) {   // 로그인이 풀려 못 받았으면 조용히 다시 로그인해서 한 번 더
      return silentLogin().then(function (q) { if (q && ok(q)) return download(); throw e; });
    }).then(function (txt) {
      var d = JSON.parse(txt);
      if (window.caches) caches.open(CK).then(function (c) { c.put(CKEY, new Response(txt)); }).catch(function () {});
      return d;
    }).catch(function (err) {
      if (!window.caches) throw err;
      return caches.open(CK).then(function (c) { return c.match(CKEY); }).then(function (res) {
        if (!res) throw err;
        return res.text().then(function (t) { var d = JSON.parse(t); d.__offline = true; return d; });
      });
    });
  }
  function logout() { lsSet(AK, null); lsSet(RK, null); return sb.auth.signOut().then(function () { if (window.caches) caches.delete(CK); }); }
  function fatal(e) {
    overlay('화면을 열지 못했습니다: ' + ((e && e.message) || e), 'err');
  }
  return { gate: gate, loadData: loadData, logout: logout, fatal: fatal, client: sb };
})();
