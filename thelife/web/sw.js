/* The Novelist — 서비스 워커.
   원칙: '항상 네트워크 먼저(network-first)'.
   고친 코드를 폰에서 바로바로 확인해야 하므로, 캐시가 옛 화면을 보여주면 안 된다.
   캐시는 오직 '인터넷이 끊겼을 때'의 대비책으로만 쓴다. */
const CACHE = "novelist-v1";
const SHELL = [
  "/writer",
  "/static/writer.css",
  "/static/writer.js",
  "/static/style.css",
  "/static/icons/icon-192.png",
];

self.addEventListener("install", (e) => {
  self.skipWaiting();                       // 새 버전이 곧바로 적용되게
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;                       // 저장 등 쓰기 요청은 그대로
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;        // 외부 요청은 관여 안 함
  // API 응답은 절대 캐시하지 않는다 (오래된 원고/설정이 보이면 안 됨)
  if (url.pathname.startsWith("/api/")) return;

  e.respondWith((async () => {
    try {
      const fresh = await fetch(req);                     // 항상 최신 우선
      if (fresh && fresh.ok) {
        const copy = fresh.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      }
      return fresh;
    } catch (err) {
      const hit = await caches.match(req);                // 오프라인일 때만 캐시
      return hit || caches.match("/writer");
    }
  })());
});
