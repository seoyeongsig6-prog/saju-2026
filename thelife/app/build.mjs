// 웹 자산(../web)을 네이티브 앱 www/ 로 굽는 빌드 스크립트.
//  1) ../web 를 www 로 복사
//  2) www/app-config.js 생성 — API 서버 주소 + RevenueCat 키/상품ID 주입
//  3) iap/iap.src.js 를 www/iap.js 로 번들 (RevenueCat 플러그인 포함)
//  4) www/writer.html 에 app-config.js, iap.js <script> 삽입 (원본 web/ 은 건드리지 않음)
//
// 설정은 환경변수로 덮어쓴다 (없으면 아래 기본값/placeholder 사용):
//   API_BASE       배포된 백엔드 주소 (예: https://thelife.onrender.com)
//   RC_IOS_KEY     RevenueCat iOS 공개 SDK 키 (appl_...)
//   RC_ANDROID_KEY RevenueCat Android 공개 SDK 키 (goog_...)
//   PRODUCT_LIGHT  라이트 구독 상품 ID (App Store/Play에 등록한 값)
//   PRODUCT_PRO    프로 구독 상품 ID
import { cpSync, rmSync, existsSync, readFileSync, writeFileSync, mkdirSync,
         readdirSync, unlinkSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const here = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(here, "..", "web");
const WWW = resolve(here, "www");

const cfg = {
  API_BASE:       process.env.API_BASE       || "https://thelife.onrender.com",
  RC_IOS_KEY:     process.env.RC_IOS_KEY     || "appl_REPLACE_ME",
  RC_ANDROID_KEY: process.env.RC_ANDROID_KEY || "goog_REPLACE_ME",
  PRODUCT_LIGHT:  process.env.PRODUCT_LIGHT  || "novelist.light.monthly",
  PRODUCT_PRO:    process.env.PRODUCT_PRO    || "novelist.pro.monthly",
};

// 1) 웹 자산 복사
if (!existsSync(WEB)) { console.error("web/ 폴더를 찾을 수 없어요:", WEB); process.exit(1); }
rmSync(WWW, { recursive: true, force: true });
mkdirSync(WWW, { recursive: true });
cpSync(WEB, WWW, { recursive: true });

// 1-b) 웹은 자산을 /static/ 로 서빙하지만, 앱 www 안에서는 파일이 평면으로 놓인다.
//      모든 html 의 절대경로 /static/ 을 상대경로로 바꾼다.
for (const f of readdirSync(WWW)) {
  if (!f.endsWith(".html")) continue;
  const p = resolve(WWW, f);
  writeFileSync(p, readFileSync(p, "utf8").replaceAll("/static/", ""));
}

// 2) app-config.js — writer.js 보다 먼저 로드되어 전역 설정을 심는다
writeFileSync(resolve(WWW, "app-config.js"),
  `/* 빌드 시 자동 생성 — 직접 수정 금지 */\n` +
  `window.NOVELIST_API_BASE=${JSON.stringify(cfg.API_BASE)};\n` +
  `window.NOVELIST_IAP_CONFIG=${JSON.stringify({
    iosKey: cfg.RC_IOS_KEY, androidKey: cfg.RC_ANDROID_KEY,
    products: { light: cfg.PRODUCT_LIGHT, pro: cfg.PRODUCT_PRO },
  })};\n`);

// 3) IAP 브리지 번들 (RevenueCat 플러그인을 포함해 window.NovelistIAP 로 노출)
await build({
  entryPoints: [resolve(here, "iap", "iap.src.js")],
  outfile: resolve(WWW, "iap.js"),
  bundle: true, format: "iife", target: "es2019", minify: true,
});

// 4) 앱의 진입 화면은 '더 노벨리스트'(writer.html) 다. Capacitor 는 www/index.html 을
//    로드하므로, 스크립트를 주입한 writer.html 을 index.html 로 굽는다.
let html = readFileSync(resolve(WWW, "writer.html"), "utf8");
if (!html.includes("app-config.js")) {          // app-config 는 writer.js 보다 먼저
  html = html.replace(/<script([^>]*)src=["']writer\.js["']([^>]*)>/,
    `<script src="app-config.js"></script>\n  <script$1src="writer.js"$2>`);
}
if (!html.includes("iap.js")) {                 // iap 브리지는 마지막에
  html = html.replace("</body>", `  <script src="iap.js"></script>\n</body>`);
}
writeFileSync(resolve(WWW, "index.html"), html);
unlinkSync(resolve(WWW, "writer.html"));         // 중복 방지 — 진입은 index.html 하나로

console.log("빌드 완료 → www/");
console.log("  API_BASE   :", cfg.API_BASE);
console.log("  RC iOS key :", cfg.RC_IOS_KEY.slice(0, 10) + "…");
console.log("  상품 ID    : light=" + cfg.PRODUCT_LIGHT + "  pro=" + cfg.PRODUCT_PRO);
if (cfg.RC_IOS_KEY.includes("REPLACE") || cfg.API_BASE.includes("thelife.onrender"))
  console.log("\n⚠  아직 placeholder 값이 있어요. README 의 '환경변수'를 채워 다시 빌드하세요.");
