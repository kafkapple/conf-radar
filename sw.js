// 오프라인 동작. 데이터가 하루 1회만 바뀌므로 캐시 전략이 단순해도 된다.
//
// - 문서(HTML) = network-first: 온라인이면 항상 최신, 끊기면 마지막 성공본을 보여준다.
//   cache-first 로 하면 마감이 지난 낡은 페이지를 계속 보여주게 되어 이 도구에서는 위험하다.
// - 나머지 정적 자산 = cache-first: 아이콘·매니페스트는 거의 안 바뀐다.
const CACHE = "conf-radar-v1";
const SHELL = ["./", "./index.html", "./manifest.webmanifest",
               "./icons/icon-180.png", "./icons/icon-192.png", "./icons/icon-512.png"];

self.addEventListener("install", e => {
  // 일부 자산이 실패해도 설치는 진행한다. all-or-nothing 이면 아이콘 하나로 오프라인이 통째로 죽는다.
  e.waitUntil(caches.open(CACHE)
    .then(c => Promise.allSettled(SHELL.map(u => c.add(u))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  if (req.mode === "navigate" || req.destination === "document"){
    e.respondWith(fetch(req)
      .then(res => { const cp = res.clone(); caches.open(CACHE).then(c => c.put(req, cp)); return res; })
      .catch(() => caches.match(req).then(r => r || caches.match("./index.html"))));
  } else {
    e.respondWith(caches.match(req).then(r => r || fetch(req).then(res => {
      const cp = res.clone(); caches.open(CACHE).then(c => c.put(req, cp)); return res;
    })));
  }
});
