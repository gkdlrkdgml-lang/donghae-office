// 인터넷이 잠깐 끊겨도 마지막으로 받은 화면과 데이터를 계속 보여 주기 위한 캐시.
// 항상 새 파일을 먼저 받아 보고, 실패할 때만 저장해 둔 것을 씁니다.
var CACHE = 'donghae-office-v6';
self.addEventListener('activate', function (e) { e.waitUntil(Promise.all([caches.delete('donghae-office-v1'), caches.delete('donghae-office-v2'), caches.delete('donghae-office-v3')])); });
self.addEventListener('install', function (e) { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  if (new URL(e.request.url).origin !== self.location.origin) return;   // 다른 사이트(로그인·자료 저장소)는 저장하지 않음
  if (/\/data\//.test(e.request.url)) return;
  e.respondWith(
    fetch(e.request.mode === 'navigate' ? e.request.url : e.request, { cache: 'no-cache' }).then(function (res) {   // 브라우저 임시 저장(10분)을 건너뛰고 새 파일 확인
      var copy = res.clone();
      caches.open(CACHE).then(function (c) { c.put(e.request.url.split('?')[0], copy); });
      return res;
    }).catch(function () {
      return caches.match(e.request.url.split('?')[0]);
    })
  );
});
