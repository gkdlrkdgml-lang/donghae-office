// 인터넷이 잠깐 끊겨도 마지막으로 받은 화면과 데이터를 계속 보여 주기 위한 캐시.
// 항상 새 파일을 먼저 받아 보고, 실패할 때만 저장해 둔 것을 씁니다.
var CACHE = 'donghae-office-v1';
self.addEventListener('install', function (e) { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request).then(function (res) {
      var copy = res.clone();
      caches.open(CACHE).then(function (c) { c.put(e.request.url.split('?')[0], copy); });
      return res;
    }).catch(function () {
      return caches.match(e.request.url.split('?')[0]);
    })
  );
});
