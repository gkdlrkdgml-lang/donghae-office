/* 바탕화면·홈 화면에 앱으로 설치(PWA) — PC(Chrome·Edge), 안드로이드 태블릿, 아이패드 */
window.DHInstall = (function () {
  var deferred = null;
  var ua = navigator.userAgent || '';
  var isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);   // 아이패드(데스크톱 모드 포함)
  var isAndroid = /Android/i.test(ua), isSamsung = /SamsungBrowser/i.test(ua), isEdge = /Edg\//.test(ua);
  function installed() {
    return matchMedia('(display-mode: fullscreen), (display-mode: standalone), (display-mode: minimal-ui)').matches || navigator.standalone === true;
  }
  window.addEventListener('beforeinstallprompt', function (e) { e.preventDefault(); deferred = e; });
  window.addEventListener('appinstalled', function () { deferred = null; var b = document.getElementById('pwaBtn'); if (b) b.remove(); close(); });

  function steps() {
    if (isIOS) return ['화면 위(또는 아래) 주소창 옆의 <b>공유 버튼</b>(네모에서 위로 화살표 □↑)을 누릅니다.', '목록을 내려 <b>「홈 화면에 추가」</b>를 누릅니다.', '오른쪽 위 <b>「추가」</b>를 누르면 홈 화면에 동해시 아이콘이 생깁니다.', '<small>※ 아이패드는 <b>Safari</b>에서만 추가할 수 있습니다.</small>'];
    if (isSamsung) return ['아래쪽 <b>메뉴(≡)</b>를 누릅니다.', '<b>「현재 페이지 추가」 → 「홈 화면」</b>을 누릅니다.', '홈 화면에 생긴 동해시 아이콘으로 여시면 됩니다.'];
    if (isAndroid) return ['오른쪽 위 <b>점 세 개(⋮)</b>를 누릅니다.', '<b>「앱 설치」</b> 또는 <b>「홈 화면에 추가」</b>를 누릅니다.', '홈 화면에 생긴 동해시 아이콘으로 여시면 됩니다.'];
    return ['주소창 오른쪽 끝의 <b>설치 아이콘(⊕ 또는 모니터 모양)</b>을 누릅니다.', '안 보이면 오른쪽 위 <b>' + (isEdge ? '점 세 개(…) → 「앱」 → 「이 사이트를 앱으로 설치」' : '점 세 개(⋮) → 「전송, 저장, 공유」 → 「페이지를 앱으로 설치」') + '</b>를 누릅니다.', '바탕화면과 시작 메뉴에 동해시 아이콘이 생깁니다. 그 아이콘으로 열면 주소창 없이 전체 화면입니다.'];
  }
  var box = null;
  function close() { if (box) { box.remove(); box = null; } }
  function guide() {
    close();
    box = document.createElement('div');
    box.id = 'dhInstall';
    box.innerHTML =
      '<style>#dhInstall{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;background:rgba(20,35,60,.4);font-family:"Pretendard","Malgun Gothic",system-ui,sans-serif}' +
      '#dhInstall .c{background:#fff;border-radius:20px;padding:26px 30px;width:min(560px,92vw);box-shadow:0 18px 60px rgba(0,0,0,.3)}' +
      '#dhInstall h3{margin:0 0 4px;font-size:22px;color:#1B3A6B}#dhInstall p{margin:0 0 14px;color:#556274;font-size:15px}' +
      '#dhInstall ol{margin:0;padding-left:22px;font-size:17px;line-height:1.7;color:#22324A}#dhInstall b{color:#1B3A6B}' +
      '#dhInstall .r{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}#dhInstall button{font:inherit;font-size:16px;font-weight:800;border:0;border-radius:10px;padding:10px 18px;cursor:pointer}' +
      '#dhInstall .ok{background:#1B3A6B;color:#fff}</style>' +
      '<div class="c"><h3>바탕화면에 앱으로 설치</h3><p>' + (isIOS || isAndroid ? '태블릿' : 'PC') + '에서는 이렇게 하시면 됩니다. 설치한 아이콘으로 열면 주소창 없이 화면 전체로 보입니다.</p><ol>' +
      steps().map(function (t) { return '<li>' + t + '</li>'; }).join('') + '</ol><div class="r"><button class="ok" type="button">확인</button></div></div>';
    box.onclick = function (e) { if (e.target === box) close(); };
    box.querySelector('.ok').onclick = close;
    document.body.appendChild(box);
  }
  function open() {
    if (deferred) { var d = deferred; d.prompt(); d.userChoice.then(function (r) { if (r && r.outcome === 'accepted') deferred = null; }); return; }
    guide();
  }
  function button(parent, style) {
    if (installed() || !parent || document.getElementById('pwaBtn')) return;
    var b = document.createElement('button');
    b.id = 'pwaBtn'; b.type = 'button'; b.textContent = '⤓ 바탕화면에 설치';
    b.title = '설치하면 주소창 없이 전체 화면으로 열립니다';
    b.style.cssText = style || '';
    b.onclick = function (e) { e.stopPropagation(); open(); };
    parent.appendChild(b);
  }
  return { open: open, installed: installed, button: button };
})();
