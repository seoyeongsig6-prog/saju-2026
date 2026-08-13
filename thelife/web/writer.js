/* The Novelist — 프런트엔드 */
const $ = (s) => document.querySelector(s);

let UID = localStorage.getItem("thelife_uid");
if (!UID) {
  UID = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now());
  localStorage.setItem("thelife_uid", UID);
}
/* 네이티브 앱(Capacitor)에서는 UI가 로컬에 번들되어 뜨므로 API는 배포 서버 절대주소로 부른다.
   웹(브라우저)에서는 같은 오리진이라 빈 문자열(상대경로) 그대로 쓴다.
   앱 빌드는 www/app-config.js 에서 window.NOVELIST_API_BASE 를 주입한다. */
const IS_NATIVE = !!(window.Capacitor && typeof window.Capacitor.isNativePlatform === "function"
  && window.Capacitor.isNativePlatform());
const API_BASE = (window.NOVELIST_API_BASE || "").replace(/\/$/, "");
if (IS_NATIVE) document.body.classList.add("native");
const api = async (path, opts = {}) => {
  const url = (API_BASE && path.startsWith("/")) ? API_BASE + path : path;
  const r = await fetch(url, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-User-Id": UID, ...(opts.headers || {}) },
  });
  return r.json();
};

/* 홈 화면에 추가하면 앱처럼 실행되게 (오프라인 대비 + 전체화면).
   서비스 워커는 '네트워크 먼저'라 고친 내용이 바로바로 반영된다. */
if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

/* 화면에 쓰는 아이콘 — 이모지는 기기·폰트에 따라 깨져서 직접 그린 SVG를 쓴다 */
const ICO = {
  home: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10.5 12 4l8 6.5"/><path d="M6 9.5V20h12V9.5"/></svg>',
  menu: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/></svg>',
  gear: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.2"/><path d="M12 3v2.2M12 18.8V21M4.2 7.5l1.9 1.1M17.9 15.4l1.9 1.1M4.2 16.5l1.9-1.1M17.9 8.6l1.9-1.1"/></svg>',
  book: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h6a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H4z"/><path d="M20 5h-6a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h6z"/></svg>',
  pen: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h16"/><path d="M13 6l5 5-9 9H4v-5z"/></svg>',
  spark: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l1.8 5.2L19 11l-5.2 1.8L12 18l-1.8-5.2L5 11l5.2-1.8z"/></svg>',
  redo: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v5h-5"/></svg>',
  copy: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 5H6a2 2 0 0 0-2 2v9"/></svg>',
  down: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11"/><path d="M7.5 11 12 15.5 16.5 11"/><path d="M5 20h14"/></svg>',
  trash: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 7h15"/><path d="M9 7V5h6v2"/><path d="M6.5 7l1 13h9l1-13"/></svg>',
  edit: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4.2L19 9.2 14.8 5 4 15.8z"/><path d="m12.8 7 4.2 4.2"/><path d="M4 20h16"/></svg>',
  film: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="18" height="12" rx="2"/><path d="M8 6v12M16 6v12M3 12h18"/></svg>',
  check: '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5 10 17.5 19 7"/></svg>',
};

let WORK = null, CHAPTER = null;

/* 판매용 런치 버전 여부 — 서버 플래그.
   body.launch = 판매 빌드(자연어 설정 수정 등 제외 항목 숨김).
   body.nobody = 'AI가 본문을 대신 써주는' 기능 없음 → 그 UI만 숨긴다.
                 작가가 직접 쓰는 에디터는 모든 등급에서 항상 열려 있다(핵심 기능).
   body.nopen  = 펜(소모성 재화)을 안 쓰는 빌드 → 펜 잔액·충전 UI 숨김. */
let LAUNCH = true, DEMO_MODE = false, AI_CONNECTED = false;
let TIER = "free", LIMITS = null, TIERS_INFO = null, EXPIRES = null;
let AI_BODY = false, PENS = 0, PEN_NEEDED = false, PEN_PACKS = [];
const CONFIG_READY = (async () => {
  try {
    const cfg = await api("/api/writer/config");
    LAUNCH = !!(cfg && cfg.launch_mode);
    DEMO_MODE = !!(cfg && cfg.demo_mode);
    AI_CONNECTED = !!(cfg && cfg.ai_connected);
    AI_BODY = !!(cfg && cfg.ai_body);
    document.body.classList.toggle("launch", LAUNCH);
    document.body.classList.toggle("nobody", !AI_BODY);
    document.body.classList.toggle("nopen", !(cfg && cfg.pens_enabled));
    if (cfg) {
      TIER = cfg.tier || "free"; LIMITS = cfg.limits; TIERS_INFO = cfg.tiers; EXPIRES = cfg.expires_at;
      PENS = cfg.pens || 0; PEN_NEEDED = !!cfg.pen_needed; PEN_PACKS = cfg.pen_packs || [];
      if (cfg.sample) SAMPLE = cfg.sample;
      if (DEMO_MODE) $("#btn-settings").textContent = "미리보기";
    }
    Ads.refresh();
    renderPenBar();
  } catch (e) { /* 실패 시 런치 기본 유지 */ }
})();

/* 본문 쓰기 응답의 need(프로/펜)에 맞춰 안내하고 요금제/충전으로 보낸다. */
function handleBodyNeed(r) {
  if (r && r.need === "pro") {
    notice("본문 쓰기는 프로 구독에서만 이용할 수 있어요.\n구독 플랜에서 프로로 올려 주세요.");
    showPlans();
    return true;
  }
  if (r && r.need === "pens") {
    notice("이 앱에서는 AI 본문 대행을 제공하지 않아요. 본문을 직접 작성해 주세요.");
    showPens();
    return true;
  }
  return false;
}
function setPens(n) { if (typeof n === "number") { PENS = n; renderPenBar(); } }

/* ---------- 설정 화면 ---------- */
function showSettings() { view("w-settings"); renderSettingsPlan(); renderThemeSeg(); }
$("#btn-settings").onclick = showSettings;

/* 설정 — 데이터 내보내기 / 계정 삭제 (스토어 정책상 앱 내 필수) */
$("#btn-export").onclick = async () => {
  const d = await api("/api/writer/account/export");
  if (!d || !d.ok) { notice("내보내기에 실패했어요. 잠시 후 다시 시도해 주세요."); return; }
  const blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "the-novelist-내데이터.json";
  a.click();
  notice(`내 데이터(작품 ${(d.works || []).length}개)를 내려받았어요.`);
};
$("#btn-delacc").onclick = async () => {
  if (!await askAction("모든 작품과 데이터를 삭제할까요?\n삭제한 데이터는 되돌릴 수 없습니다.", "모두 삭제", "취소")) return;
  const r = await api("/api/writer/account", { method: "DELETE" });
  if (!r || !r.ok) { notice("삭제에 실패했어요. 잠시 후 다시 시도해 주세요."); return; }
  notice("모든 데이터를 삭제했어요.");
  showHome();
};

/* 요금제 (설정 화면) — 현재 플랜 요약 + '구독 플랜 보기·변경' 진입 */
function renderSettingsPlan() {
  const bar = $("#settings-plan");
  if (!bar || !LIMITS || !TIERS_INFO) return;
  const L = LIMITS;
  const works = L.max_works >= 100000 ? "무제한" : L.max_works + "개";
  const expTxt = EXPIRES ? ` <span class="plan-exp">~${String(EXPIRES).slice(0, 10)}까지</span>` : "";
  const sample = L.sample_daily ? `본문 예시 ${L.sample_daily}회/일` : "본문 예시 없음";
  bar.innerHTML = `
    <div class="plan-now">현재 플랜 <b>${L.label}</b>${expTxt}
      <span class="plan-lim">AI 회차 설계 ${L.max_chapters}화 · 화당 ${L.syn_chars}자 · 인물 ${L.max_characters}명 · 작품 ${works} · ${sample}</span></div>
    <button class="plan-upgrade" id="see-plans">구독 플랜 보기 · 변경</button>`;
  $("#see-plans").onclick = () => showPlans("settings");
}

/* ---------- 구독 플랜 비교 화면 ---------- */
const PLAN_ORDER = ["free", "light", "pro"];
const EMBLEM = {
  free: '<svg viewBox="0 0 48 48"><path d="M24 12c-9 0-15 6-15 15 9 0 15-6 15-15z"/><path d="M24 27v14" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round"/></svg>',
  light: '<svg viewBox="0 0 48 48"><path d="M27 6L13 27h9l-3 15 16-21h-9z"/></svg>',
  pro: '<svg viewBox="0 0 48 48"><path d="M8 34l-3-17 10 7 9-13 9 13 10-7-3 17z"/></svg>',
};
const EMBLEM_BG = {
  free: "linear-gradient(135deg,#aeaacd,#8b88ad)",
  light: "linear-gradient(135deg,#5aa0ea,#3f7fd0)",
  pro: "var(--grad)",
};
const IC = {
  book: '<svg viewBox="0 0 24 24"><path d="M4 5h6a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H4z"/><path d="M20 5h-6a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h6z"/></svg>',
  pen: '<svg viewBox="0 0 24 24"><path d="M14 4l6 6M4.5 19.5l1-4L16 5l3 3L8.5 18.5z"/></svg>',
  users: '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><path d="M16 5.6a3 3 0 0 1 0 5.8"/><path d="M20.5 20a5.5 5.5 0 0 0-3.4-5.1"/></svg>',
  stack: '<svg viewBox="0 0 24 24"><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/></svg>',
  spark: '<svg viewBox="0 0 24 24"><path d="M12 3l2.2 6L20 11l-5.8 2L12 19l-2.2-6L4 11l5.8-2z"/></svg>',
  ban: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/></svg>',
  write: '<svg viewBox="0 0 24 24"><path d="M4 20h16"/><path d="M13 6l5 5L9 20H4v-5z"/></svg>',
};
function _feat(icon, label, val, off) {
  return `<li class="${off ? "off" : ""}">${icon}<span>${label}</span><b>${val}</b></li>`;
}
let PLAN_BACK = "settings";
function showPlans(from) {
  PLAN_BACK = from || "settings";
  view("w-plans");
  $("#plans-hint").textContent = PLAN_BACK === "plot"
    ? "1,000자 본문 예시는 라이트 플랜부터 사용할 수 있어요."
    : "작품 규모와 필요한 AI 도움에 맞춰 선택하세요.";
  renderPlans();
}
function leavePlans() {
  if (PLAN_BACK === "plot" && WORK) showPlot(PLOT_OPEN);
  else if (PLAN_BACK === "wizard" && WZ) { view("w-wizard"); wzRender(); }
  else if (PLAN_BACK === "work" && WORK) openWork(WORK.id);
  else if (PLAN_BACK === "home") showHome();
  else showSettings();
}
$("#plans-back").onclick = leavePlans;
function renderPlans() {
  const box = $("#plans-list");
  if (!box || !TIERS_INFO) return;
  box.innerHTML = PLAN_ORDER.map((t) => {
    const P = TIERS_INFO[t];
    const works = P.max_works >= 100000 ? "무제한" : P.max_works + "개";
    const cur = t === TIER;
    // 이 빌드가 '실제로 하는 것'만 적는다 — 없는 기능을 플랜에 적지 않는다.
    const anyStyle = PLAN_ORDER.some((k) => TIERS_INFO[k] && TIERS_INFO[k].style_learning);
    const anyBody = PLAN_ORDER.some((k) => TIERS_INFO[k] && TIERS_INFO[k].body_writing);
    const feats = [
      _feat(IC.book, "AI 회차 줄거리", P.max_chapters + "화"),
      _feat(IC.pen, "화당 줄거리", P.syn_chars + "자"),
      _feat(IC.users, "AI 인물 생성", P.max_characters + "명"),
      _feat(IC.stack, "작품 수", works),
      _feat(IC.write, "직접 본문 쓰기", "무제한"),
      _feat(IC.spark, "본문 예시 · 약 1,000자", P.sample_daily ? `하루 ${P.sample_daily}회` : "—", !P.sample_daily),
      P.ai_daily ? _feat(IC.spark, "하루 AI 사용", P.ai_daily + "회") : "",
      anyStyle ? _feat(IC.spark, "문체 학습", P.style_learning ? "✓" : "—", !P.style_learning) : "",
      anyBody ? _feat(IC.pen, "AI 본문 대행", P.body_writing ? "✓" : "—", !P.body_writing) : "",
      _feat(IC.ban, "광고 제거", P.ads ? "—" : "✓", P.ads),
    ].join("");
    const cta = cur
      ? '<button class="plan-cta current" disabled>현재 플랜</button>'
      : `<button class="plan-cta buy" data-tier="${t}">${t === "free" ? "무료로 전환" : P.label + " 선택"}</button>`;
    return `<div class="plan-card ${t === "pro" ? "rec" : ""}">
      ${P.badge ? `<span class="plan-badge">${P.badge}</span>` : ""}
      <div class="plan-head">
        <div class="plan-emblem" style="background:${EMBLEM_BG[t]}">${EMBLEM[t]}</div>
        <div class="plan-title"><b>${P.label}</b>${P.best_for ? `<span class="plan-bestfor">${P.best_for}</span>` : ""}<small>${P.tagline}</small></div>
        <div class="plan-price">${P.price}<span>${P.period}</span></div>
      </div>
      ${P.pitch ? `<p class="plan-pitch">${P.pitch}</p>` : ""}
      ${P.highlight ? `<div class="plan-highlight">${IC.spark}<span>${P.highlight}</span></div>` : ""}
      <ul class="plan-feats">${feats}</ul>
      ${cta}</div>`;
  }).join("");
  box.querySelectorAll(".plan-cta.buy").forEach((b) => { b.onclick = () => choosePlan(b.dataset.tier); });
}
/* 결제 후 서버(RevenueCat 검증)로 등급을 재동기화하고 화면을 갱신한다. */
async function syncEntitlement() {
  const r = await api("/api/writer/entitlement", {
    method: "POST", body: JSON.stringify({ platform: IS_NATIVE ? "native" : "web" }),
  });
  if (r && r.ok) {
    TIER = r.tier; LIMITS = r.limits; EXPIRES = r.expires_at || null;
    renderPlans(); renderSettingsPlan(); Ads.refresh();
  }
  return r;
}

async function choosePlan(t) {
  if (t === "free") {
    notice("무료는 구독을 해지하면 자동으로 적용돼요.\n구독 관리는 기기의 앱스토어 · Google Play 계정에서 할 수 있어요.");
    return;
  }
  // 개발용 웹(비런치)에서는 서버 오버라이드로 미리보기 전환.
  if (!LAUNCH && !window.NovelistIAP) {
    const r = await api("/api/writer/tier", { method: "POST", body: JSON.stringify({ tier: t }) });
    if (r.ok) { TIER = r.tier; LIMITS = r.limits; renderPlans(); renderSettingsPlan(); Ads.refresh();
      notice(`${TIERS_INFO[t].label} 플랜으로 전환했어요. (미리보기)`); }
    else notice(r.error || "변경할 수 없어요.");
    return;
  }
  // 실제 앱 — 네이티브 인앱 결제(RevenueCat) 브리지로 구매.
  if (!window.NovelistIAP) {
    notice("곧 앱에서 구독을 구매할 수 있어요.\n(App Store · Google Play 결제 연결 예정)");
    return;
  }
  try {
    busy("결제를 준비하는 중…");
    const res = await window.NovelistIAP.purchase(t);   // {ok, cancelled?, error?}
    if (res && res.cancelled) { unbusy(); return; }
    if (!res || !res.ok) { unbusy(); notice(res && res.error ? res.error : "결제를 완료하지 못했어요."); return; }
    const sync = await syncEntitlement();
    unbusy();
    if (sync && sync.ok && sync.tier === t) notice(`${TIERS_INFO[t].label} 플랜이 시작됐어요. 감사합니다!`);
    else notice("결제는 됐어요. 반영까지 잠시 걸릴 수 있어요.");
  } catch (e) { unbusy(); notice("결제 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요."); }
}

/* 구매 복원 — 기기 변경·재설치 후 이전 구독을 되살린다 (스토어 심사 필수 기능). */
async function restorePurchases() {
  if (!window.NovelistIAP) { notice("앱에서만 사용할 수 있어요."); return; }
  try {
    busy("구매 내역을 확인하는 중…");
    await window.NovelistIAP.restore();
    const sync = await syncEntitlement();
    unbusy();
    notice(sync && sync.ok && sync.tier !== "free"
      ? `${TIERS_INFO[sync.tier].label} 구독을 되살렸어요.`
      : "되살릴 활성 구독이 없어요.");
  } catch (e) { unbusy(); notice("구매 복원 중 문제가 생겼어요."); }
}

/* 광고 — 무료 요금제에서만. 실제 AdMob은 네이티브 래핑 단계에서 이 함수 안을 교체한다. */
const Ads = {
  on() { return !!(LIMITS && LIMITS.ads); },   // 무료 티어 = 광고 대상
  refresh() {
    const show = this.on();
    $("#ad-banner").classList.toggle("hidden", !show);
    document.body.classList.toggle("has-ad", show);
    // 네이티브: show ? AdMob.showBanner() : AdMob.hideBanner();
  },
  _last: 0,
  maybeInterstitial() {                          // 무거운 동작 뒤, 쿨다운 두고 한 번
    if (!this.on()) return;
    const now = Date.now();
    if (now - this._last < 90000) return;
    this._last = now;
    const m = $("#ad-interstitial"), btn = $("#ad-close");
    m.classList.remove("hidden");
    let n = 3; btn.disabled = true; btn.textContent = `닫기 (${n})`;
    const t = setInterval(() => {
      n -= 1;
      if (n <= 0) { clearInterval(t); btn.disabled = false; btn.textContent = "닫기"; }
      else btn.textContent = `닫기 (${n})`;
    }, 1000);
    btn.onclick = () => { if (!btn.disabled) m.classList.add("hidden"); };
    // 네이티브: AdMob.showInterstitial();
  },
};
$("#ad-upsell").onclick = () => {
  const open = ["w-wizard", "w-plot", "w-work", "w-home", "w-settings"]
    .find((id) => !$("#" + id).classList.contains("hidden"));
  const from = ({ "w-wizard": "wizard", "w-plot": "plot", "w-work": "work",
                  "w-home": "home", "w-settings": "settings" })[open] || "settings";
  showPlans(from);
};

/* ---------- 테마 (밝게/어둡게 — 기본 밝게, 설정 화면에서 전환) ---------- */
function applyTheme(t) {
  document.body.dataset.theme = t;
  localStorage.setItem("thelife_theme", t);
  renderThemeSeg();
}
function renderThemeSeg() {
  const seg = $("#theme-seg");
  if (!seg) return;
  const cur = document.body.dataset.theme || "light";
  seg.innerHTML = [["light", "밝게"], ["dark", "어둡게"]]
    .map(([v, l]) => `<button data-th="${v}" class="${cur === v ? "on" : ""}">${l}</button>`).join("");
  seg.querySelectorAll("button").forEach((b) => { b.onclick = () => applyTheme(b.dataset.th); });
}
applyTheme(localStorage.getItem("thelife_theme") || "light");

function view(id) {
  ["w-home", "w-settings", "w-plans", "w-pens", "w-wizard", "w-build", "w-work", "w-plot", "w-editor"]
    .forEach((v) =>
    $(`#${v}`).classList.toggle("hidden", v !== id));
  const focus = ["w-wizard", "w-build", "w-editor"].includes(id);
  document.body.classList.toggle("focus-mode", focus);
  const active = ({ "w-home": "home", "w-work": "home", "w-plot": "home",
                    "w-settings": "settings", "w-plans": "plans", "w-pens": "settings" })[id] || "";
  document.querySelectorAll("#app-nav [data-nav]").forEach((b) => {
    const on = b.dataset.nav === active;
    b.classList.toggle("active", on);
    if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
}

document.querySelectorAll("#app-nav [data-nav]").forEach((b) => {
  b.onclick = () => {
    const to = b.dataset.nav;
    if (to === "home") { showHome(); return; }
    if (to === "new") { startWizard(); return; }
    if (to === "plans") { showPlans("home"); return; }
    if (to === "settings") { showSettings(); return; }
  };
});

/* ---------- 펜 충전 화면 ---------- */
function showPens() { view("w-pens"); renderPens(); }
function showBack() { if (WORK) openWork(WORK.id); else showSettings(); }
function renderPenBar() {
  const bar = $("#pen-bar");
  if (!bar) return;
  bar.classList.toggle("hidden", !PEN_NEEDED);   // 개인 서버(펜 불필요)에선 숨김
  if (!PEN_NEEDED) return;
  bar.innerHTML = `남은 펜 <b>${PENS}</b>
    <span class="pen-sub">본문 1편 = 펜 1개</span>
    <button class="pen-charge" onclick="showPens()">＋ 충전</button>`;
  const pc = $("#pen-count"); if (pc) pc.textContent = PENS;
}
function renderPens() {
  const pc = $("#pen-count"); if (pc) pc.textContent = PENS;
  const box = $("#pen-packs");
  if (!box) return;
  box.innerHTML = (PEN_PACKS || []).map((p) => `
    <div class="pen-pack">
      ${p.badge ? `<span class="pen-badge">${p.badge}</span>` : ""}
      <div class="pen-pack-top"><b>펜 ${p.count}개</b><span class="pen-per">${p.per || ""}</span></div>
      <button class="pen-buy" data-product="${p.product}" data-count="${p.count}">${p.price} 구매</button>
    </div>`).join("");
  box.querySelectorAll(".pen-buy").forEach((b) => {
    b.onclick = () => buyPens(b.dataset.product, +b.dataset.count);
  });
}
async function buyPens(productId, count) {
  if (!window.NovelistIAP) {
    notice("곧 앱에서 펜을 구매할 수 있어요.\n(App Store · Google Play 결제 연결 예정)");
    return;
  }
  try {
    busy("결제를 준비하는 중…");
    const res = await window.NovelistIAP.purchaseProduct(productId);   // {ok, cancelled?, error?}
    if (res && res.cancelled) { unbusy(); return; }
    if (!res || !res.ok) { unbusy(); notice(res && res.error ? res.error : "결제를 완료하지 못했어요."); return; }
    const cr = await api("/api/writer/pens/purchase", {
      method: "POST", body: JSON.stringify({ product_id: productId }),
    });
    unbusy();
    if (cr && cr.ok) { setPens(cr.pens); renderPens();
      notice(`펜 ${count}개를 충전했어요. 이제 본문을 쓸 수 있어요!`); }
    else notice((cr && cr.error) || "충전 반영이 지연되고 있어요. 잠시 후 다시 확인해 주세요.");
  } catch (e) { unbusy(); notice("결제 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요."); }
}
function notice(t) {
  $("#notice-text").textContent = t;
  $("#notice-undo").classList.add("hidden");
  $("#notice").classList.remove("hidden");
}
$("#notice-close").onclick = () => $("#notice").classList.add("hidden");
function askAction(text, okLabel = "확인", cancelLabel = "취소") {
  return new Promise((resolve) => {
    const modal = $("#action-confirm");
    const ok = $("#action-confirm-ok");
    const cancel = $("#action-confirm-cancel");
    $("#action-confirm-text").textContent = text;
    ok.textContent = okLabel;
    cancel.textContent = cancelLabel;
    const finish = (answer) => {
      modal.classList.add("hidden");
      ok.onclick = null; cancel.onclick = null;
      resolve(answer);
    };
    ok.onclick = () => finish(true);
    cancel.onclick = () => finish(false);
    modal.classList.remove("hidden");
  });
}
function busy(t) { $("#busy-text").textContent = t; $("#busy").classList.remove("hidden"); }
function unbusy() { $("#busy").classList.add("hidden"); }

/* ---------- 작품 목록 ---------- */
async function showHome() {
  view("w-home");
  const d = await api("/api/writer/works");
  const box = $("#w-list");
  box.innerHTML = "";
  const works = d.works || [];
  $("#w-empty").classList.toggle("hidden", works.length > 0);
  $("#w-new").textContent = works.length ? "새 작품 만들기" : "첫 작품 만들기";
  works.forEach((w) => {
    const el = document.createElement("button");
    el.className = "w-item";
    const pct = Math.min(100, Math.round((w.written / Math.max(1, w.total_chapters)) * 100));
    el.innerHTML = `<span class="del" data-id="${w.id}" aria-label="작품 삭제">✕</span>
      <span class="work-copy"><small>${escapeHtml(w.genre)}</small><b>${escapeHtml(w.title)}</b>
      <span class="work-progress"><i style="width:${pct}%"></i></span>
      <em>${w.written}/${w.total_chapters}화 집필 · ${pct}%</em></span>
      <span class="work-enter">이어 쓰기</span>`;
    el.onclick = (ev) => {
      if (ev.target.classList.contains("del")) return delWork(w.id, w.title);
      openWork(w.id);
    };
    box.appendChild(el);
  });
}
async function delWork(id, title) {
  if (!await askAction(`『${title}』 작품을 삭제할까요?`, "삭제", "취소")) return;
  const r = await api(`/api/writer/works/${id}`, { method: "DELETE" });
  if (!r || !r.ok) { notice((r && r.error) || "삭제하지 못했어요."); return; }
  await showHome();
}
/* ---------- 새 작품 = 작품설명서 빌더로 바로 ---------- */
const bdVal = (id) => $("#" + id).value.trim();

/* 새 작품 = 단계별 설계(위저드). 상세 폼(w-build)은 '직접 다 채우기'로 남겨둔다. */
$("#w-new").onclick = () => startWizard();
function showDetailBuilder() {
  view("w-build");
  if (!$("#bd-chars").children.length) { bdAddChar(); bdAddChar(); }
  if (!$("#bd-canon").children.length) { bdAddCanon(); }
}

/* 선택지 + '기타(직접 입력)' 패턴 */
const ROLE_OPTS = ["적대자(메인 빌런)", "서브 빌런", "조력자", "멘토·스승", "애정상대",
  "라이벌", "동료", "가족", "부하·수하", "상관·윗사람", "배신자", "전령·정보원", "관문 수호자", "기타"];
const REL_OPTS = ["연인·애정", "친구·동료", "스승·사제", "가족·혈연", "라이벌·경쟁", "원수·적대",
  "상하관계", "협력자", "은인", "배신자", "첫사랑", "소꿉친구", "계약관계", "기타"];

function optSelectHtml(cls, opts, ph) {
  return `<select class="${cls}"><option value="">${ph}</option>` +
    opts.map((x) => `<option>${x}</option>`).join("") + `</select>` +
    `<input class="${cls}-other hidden" placeholder="직접 입력">`;
}
function isEtc(sel) { return !!sel.value && sel.value.indexOf("기타") === 0; }
function wireOther(sel, other) {
  const upd = () => other.classList.toggle("hidden", !isEtc(sel));
  sel.addEventListener("change", upd); upd();
}
function getOtherSelect(sel, other) { return isEtc(sel) ? other.value.trim() : (sel.value || "").trim(); }
function setOtherSelect(sel, other, val) {
  val = (val || "").trim();
  const match = [...sel.options].find((o) => (o.value || o.text) === val);
  if (!val) { sel.value = ""; other.value = ""; }
  else if (match) { sel.value = match.value || match.text; other.value = ""; }
  else {
    const etc = [...sel.options].find((o) => o.text.indexOf("기타") === 0);
    sel.value = etc ? (etc.value || etc.text) : ""; other.value = val;
  }
  other.classList.toggle("hidden", !isEtc(sel));
}

// 장르·문체 선택창의 '기타' 토글 초기화
wireOther($("#bd-genre-sel"), $("#bd-genre-other"));
wireOther($("#bd-style-sel"), $("#bd-style-other"));
const bdGenre = () => getOtherSelect($("#bd-genre-sel"), $("#bd-genre-other"));
const bdStyle = () => getOtherSelect($("#bd-style-sel"), $("#bd-style-other"));

/* ✕ 삭제 → 되돌리기 (빌더 행: 인물·고유명사·회차) */
function readChar(r) {
  return {
    name: r.querySelector(".c-name").value,
    role: getOtherSelect(r.querySelector(".c-role"), r.querySelector(".c-role-other")),
    relation: getOtherSelect(r.querySelector(".c-rel"), r.querySelector(".c-rel-other")),
    want: r.querySelector(".c-want").value, need: r.querySelector(".c-need").value,
    secret: r.querySelector(".c-secret").value,
  };
}
const readCanonRow = (r) => ({ name: r.querySelector(".cn-name").value, desc: r.querySelector(".cn-desc").value });
const readOutlineRow = (r) => ({
  no: Number(r.querySelector(".o-no").value) || "", title: r.querySelector(".o-title").value,
  content: r.querySelector(".o-content").value,
});
async function removeRowConfirm(el, label) {
  if (!await askAction(`이 ${label} 항목을 삭제할까요?`, "삭제", "취소")) return false;
  el.remove();
  return true;
}

function bdAddChar(d = {}) {
  const el = document.createElement("div");
  el.className = "bd-char-row";
  el.innerHTML = `
    <button class="row-del" title="삭제">✕</button>
    <input class="c-name" placeholder="이름">
    <label class="cf"><span>역할</span>${optSelectHtml("c-role", ROLE_OPTS, "역할 선택")}</label>
    <label class="cf"><span>주인공과의 관계</span>${optSelectHtml("c-rel", REL_OPTS, "관계 선택")}</label>
    <div class="row2">
      <input class="c-want" placeholder="욕망 — 겉으로 쫓는 것">
      <input class="c-need" placeholder="결핍 — 진짜 필요한 것">
    </div>
    <input class="c-secret" placeholder="비밀 (선택) — 숨기는 것">`;
  el.querySelector(".c-name").value = d.name || "";
  setOtherSelect(el.querySelector(".c-role"), el.querySelector(".c-role-other"), d.role);
  setOtherSelect(el.querySelector(".c-rel"), el.querySelector(".c-rel-other"), d.relation);
  el.querySelector(".c-want").value = d.want || "";
  el.querySelector(".c-need").value = d.need || "";
  el.querySelector(".c-secret").value = d.secret || "";
  wireOther(el.querySelector(".c-role"), el.querySelector(".c-role-other"));
  wireOther(el.querySelector(".c-rel"), el.querySelector(".c-rel-other"));
  el.querySelector(".row-del").onclick = () => removeRowConfirm(el, "인물");
  $("#bd-chars").appendChild(el);
}

function bdAddCanon(d = {}) {
  const el = document.createElement("div");
  el.className = "bd-canon-row";
  el.innerHTML = `<button class="row-del" title="삭제">✕</button>
    <div class="row2"><input class="cn-name" placeholder="이름"><input class="cn-desc" placeholder="설명 (선택)"></div>`;
  el.querySelector(".cn-name").value = d.name || "";
  el.querySelector(".cn-desc").value = d.desc || "";
  el.querySelector(".row-del").onclick = () => removeRowConfirm(el, "고유명사");
  $("#bd-canon").appendChild(el);
}

function bdAddOutline(d = {}) {
  const el = document.createElement("div");
  el.className = "bd-outline-row";
  el.innerHTML = `<button class="row-del" title="삭제">✕</button>
    <div class="o-head"><input class="o-no" type="number" min="1" placeholder="화"><input class="o-title" placeholder="제목"></div>
    <textarea class="o-content" rows="5" placeholder="이 화의 핵심 사건 — 누가 무엇을 하고 무엇이 바뀌는지"></textarea>`;
  el.querySelector(".o-no").value = d.no || "";
  el.querySelector(".o-title").value = d.title || "";
  el.querySelector(".o-content").value = d.content || "";
  el.querySelector(".row-del").onclick = () => removeRowConfirm(el, "회차");
  $("#bd-outline").appendChild(el);
}

$("#bd-add-char").onclick = () => bdAddChar();
$("#bd-add-canon").onclick = () => bdAddCanon();
$("#bd-add-outline").onclick = () => {
  const have = [...$("#bd-outline").querySelectorAll(".o-no")].map((i) => Number(i.value) || 0);
  bdAddOutline({ no: (Math.max(0, ...have) || 0) + 1 });
};
/* 1화~끝화까지 빈 줄거리 칸을 한 번에 만든다 (직접 쓰기용) */
$("#bd-fill-outline").onclick = () => {
  const total = Math.max(1, Math.min(Number($("#bd-total").value) || 25, 200));
  const have = new Set([...$("#bd-outline").querySelectorAll(".o-no")].map((i) => Number(i.value)));
  let added = 0;
  for (let n = 1; n <= total; n++) {
    if (!have.has(n)) { bdAddOutline({ no: n }); added++; }
  }
  bdSortOutline();
  if (!added) notice("이미 1~" + total + "화 칸이 다 있어요.");
};
/* 화 번호 순으로 정렬해 다시 배치 */
function bdSortOutline() {
  const box = $("#bd-outline");
  [...box.children]
    .sort((a, b) => (Number(a.querySelector(".o-no").value) || 0) - (Number(b.querySelector(".o-no").value) || 0))
    .forEach((el) => box.appendChild(el));
}

function bdCollect() {
  return {
    title: bdVal("bd-title"), genre: bdGenre(),
    total_chapters: Number($("#bd-total").value) || 25,
    keywords: bdVal("bd-keywords"),
    logline: bdVal("bd-logline"), intent: bdVal("bd-intent"),
    world_setting: bdVal("bd-world"), world_rules: bdVal("bd-rules"), taboos: bdVal("bd-taboos"),
    protagonist: {
      name: bdVal("bd-p-name"), age: bdVal("bd-p-age"), job: bdVal("bd-p-job"),
      personality: bdVal("bd-p-personality"), want: bdVal("bd-p-want"),
      need: bdVal("bd-p-need"), secret: bdVal("bd-p-secret"), arc: bdVal("bd-p-arc"),
    },
    characters: [...$("#bd-chars").querySelectorAll(".bd-char-row")].map((r) => ({
      name: r.querySelector(".c-name").value.trim(),
      role: getOtherSelect(r.querySelector(".c-role"), r.querySelector(".c-role-other")),
      relation: getOtherSelect(r.querySelector(".c-rel"), r.querySelector(".c-rel-other")),
      want: r.querySelector(".c-want").value.trim(),
      need: r.querySelector(".c-need").value.trim(), secret: r.querySelector(".c-secret").value.trim(),
    })).filter((c) => c.name),
    canon: [...$("#bd-canon").querySelectorAll(".bd-canon-row")].map((r) => ({
      name: r.querySelector(".cn-name").value.trim(), desc: r.querySelector(".cn-desc").value.trim(),
    })).filter((c) => c.name),
    style: bdStyle(), style_sample: bdVal("bd-sample"), ending: bdVal("bd-ending"),
    outline: [...$("#bd-outline").querySelectorAll(".bd-outline-row")].map((r) => ({
      no: Number(r.querySelector(".o-no").value) || 0,
      title: r.querySelector(".o-title").value.trim(), content: r.querySelector(".o-content").value.trim(),
    })).filter((o) => o.no >= 1 && (o.title || o.content)),
  };
}

function bdSetIfEmpty(id, val) { const e = $("#" + id); if (val && !e.value.trim()) e.value = val; }
function bdFill(d) {
  d = d || {};
  [["bd-title", d.title], ["bd-logline", d.logline], ["bd-intent", d.intent],
   ["bd-world", d.world_setting], ["bd-rules", d.world_rules], ["bd-taboos", d.taboos],
   ["bd-ending", d.ending]].forEach(([id, v]) => bdSetIfEmpty(id, v));
  if (d.style && !bdStyle()) setOtherSelect($("#bd-style-sel"), $("#bd-style-other"), d.style);
  const p = d.protagonist || {};
  [["bd-p-name", p.name], ["bd-p-age", p.age], ["bd-p-job", p.job],
   ["bd-p-personality", p.personality], ["bd-p-want", p.want], ["bd-p-need", p.need],
   ["bd-p-secret", p.secret], ["bd-p-arc", p.arc]].forEach(([id, v]) => bdSetIfEmpty(id, v));
  const allEmpty = (sel, f) => [...$(sel).children].every((r) => !f(r));
  if (Array.isArray(d.characters) && d.characters.length &&
      allEmpty("#bd-chars", (r) => r.querySelector(".c-name").value.trim())) {
    $("#bd-chars").innerHTML = ""; d.characters.forEach(bdAddChar);
  }
  if (Array.isArray(d.canon) && d.canon.length &&
      allEmpty("#bd-canon", (r) => r.querySelector(".cn-name").value.trim())) {
    $("#bd-canon").innerHTML = ""; d.canon.forEach(bdAddCanon);
  }
}

/* 초안 생성에서 AI가 채우는 부분만 비운다 (로그라인·결말·표본 등 씨앗은 유지) */
function bdResetGenerated() {
  ["bd-world", "bd-rules", "bd-taboos", "bd-p-name", "bd-p-age", "bd-p-job",
   "bd-p-personality", "bd-p-want", "bd-p-need", "bd-p-secret", "bd-p-arc"]
    .forEach((id) => { $("#" + id).value = ""; });
  setOtherSelect($("#bd-style-sel"), $("#bd-style-other"), "");
  $("#bd-chars").innerHTML = "";
  $("#bd-canon").innerHTML = "";
}

async function bdDraft() {
  const b = bdCollect();
  if (!b.logline && !b.genre && !b.keywords) {
    notice("장르·로그라인·키워드 중 하나는 먼저 알려주세요. 거기서 상세 기획을 지어드려요."); return;
  }
  busy("AI가 상세 기획 초안을 짜는 중… (20초쯤)");
  const r = await api("/api/writer/brief/draft", { method: "POST", body: JSON.stringify(b) });
  unbusy();
  if (!r.ok) { notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : "")); return; }
  bdFill(r.draft);
  notice("초안을 채웠어요. 각 칸을 직접 고치거나, 다시 짓고 싶은 칸은 비우고 ‘AI 초안 생성’을 다시 누르세요.");
}

$("#bd-ai-draft").onclick = bdDraft;
$("#bd-ai-redraft").onclick = async () => {
  if (!await askAction("AI가 채운 내용을 비우고 처음부터 다시 만들까요?\n로그라인·결말·문체 표본은 유지됩니다.", "다시 만들기", "취소")) return;
  bdResetGenerated();
  bdDraft();
};

$("#bd-ai-outline").onclick = async () => {
  const b = bdCollect();
  if (!b.logline && !b.ending && !b.world_setting) {
    notice("회차 전개를 짜려면 로그라인·세계관·결말 중 하나는 채워주세요."); return;
  }
  if ($("#bd-outline").children.length &&
      !await askAction("이미 만든 회차 전개를 지우고 새로 만들까요?", "다시 만들기", "취소")) return;
  busy(`AI가 ${b.total_chapters}화 전개를 짜는 중… (30초~1분)`);
  const r = await api("/api/writer/brief/outline", { method: "POST", body: JSON.stringify(b) });
  unbusy();
  if (!r.ok) { notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : "")); return; }
  $("#bd-outline").innerHTML = "";
  (r.outline || []).forEach(bdAddOutline);
  const base = `${(r.outline || []).length}개 회차 전개를 채웠어요.`;
  notice(r.capped
    ? `${base}\n\n현재 플랜은 ${r.tier_max}화까지만 자동 생성돼요. 더 많은 화는 상위 플랜에서 (또는 직접 작성).`
    : `${base} 각 칸을 자유롭게 고치세요.`);
};

$("#bd-go").onclick = async () => {
  const b = bdCollect();
  if (!b.genre) { notice("장르를 선택해 주세요. (필수)"); return; }
  if (!b.logline) { notice("로그라인을 입력해 주세요. (필수)"); return; }
  if (!b.intent) { notice("기획 의도를 입력해 주세요. (필수)"); return; }
  busy("설명서를 정리하고 설계도(인물·관계·15비트)를 만드는 중… (30초쯤)");
  const r = await api("/api/writer/works/build", { method: "POST", body: JSON.stringify(b) });
  unbusy();
  if (!r.ok) {
    notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : "")); return;
  }
  if (r.outline_chapters >= 3) {
    notice(`${r.outline_chapters}개 회차의 지정 내용이 저장됐어요.\n각 회차는 이 전개 그대로 집필됩니다.`);
  }
  await openWork(r.id);
  Ads.maybeInterstitial();   // 무료: 작품 생성 뒤 전면 광고 (쿨다운)
};

/* ---------- 작품 화면 ---------- */
async function openWork(id) {
  const d = await api(`/api/writer/works/${id}`);
  if (!d.ok) { notice(d.error); return; }
  WORK = d.work;
  WORK.chapters = d.chapters;
  view("w-work");
  $("#wk-title").textContent = "작품";
  $("#wk-name").textContent = WORK.title;
  const written = d.chapters.filter((ch) => (ch.chars || 0) > 0).length;
  $("#wk-progress").textContent = `${written}/${WORK.total_chapters}화 집필`;
  renderChapters();
  renderBible();
  renderPenBar();
  wtab("chapters");
}

document.querySelectorAll(".wtab").forEach((t) => { t.onclick = () => wtab(t.dataset.wtab); });
function wtab(name) {
  document.querySelectorAll(".wtab").forEach((t) =>
    t.classList.toggle("active", t.dataset.wtab === name));
  $("#wt-chapters").classList.toggle("hidden", name !== "chapters");
  $("#wt-bible").classList.toggle("hidden", name !== "bible");
}

const escapeHtml = (s) => (s || "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function renderChapters() {
  const box = $("#ch-list");
  box.innerHTML = "";
  const written = WORK.chapters.filter((ch) => (ch.chars || 0) > 0).length;
  if (!written) {
    box.innerHTML = `<p class="hint">아직 쓴 회차가 없어요. 회차별 줄거리는 위 '회차별 줄거리'에서 보고 고칠 수 있어요.<br>
      아래 '1화 쓰기'를 누르면 바로 집필을 시작할 수 있어요.</p>`;
  }
  // 이미 쓴 회차만 목록에 보여준다 (예정 회차·비트 라벨은 표시하지 않음).
  WORK.chapters.forEach((ch) => {
    const el = document.createElement("button");
    el.className = "ch-item";
    const n = ch.chars || 0;
    el.innerHTML = `<span class="ch-no">${ch.no}화</span> ${escapeHtml(ch.title) || ""}` +
      `<span class="ch-len">${n ? n.toLocaleString() + "자" : "아직 안 씀"}</span>`;
    el.onclick = () => openChapter(ch.id);
    box.appendChild(el);
  });
  // 작가가 직접 쓰는 입구 — 등급과 무관하게 항상 있다.
  const nos = WORK.chapters.map((c) => c.no);
  let next = 1;
  while (nos.includes(next)) next++;
  if (next <= (WORK.total_chapters || 0)) {
    const go = document.createElement("button");
    go.className = "ch-new primary";
    go.innerHTML = ICO.pen + `<span>${next}화 쓰기</span>`;
    go.onclick = () => startWriting(next);
    box.appendChild(go);
  }
}

/* 빈 회차를 열고(없으면 만들고) 바로 에디터로 — AI도 펜도 쓰지 않는다. */
async function startWriting(no) {
  const r = await api(`/api/writer/works/${WORK.id}/chapters/blank`, {
    method: "POST", body: JSON.stringify({ no: no || 0 }),
  });
  if (!r.ok) { notice(r.error || "회차를 열 수 없어요."); return; }
  if (r.created) {
    const d = await api(`/api/writer/works/${WORK.id}`);
    if (d.ok) { WORK = d.work; WORK.chapters = d.chapters; }
  }
  openChapter(r.id);
}

function editOutline(n, el, after) {
  const redraw = after || renderChapters;
  const o = (WORK.outline || []).find((x) => x.no === n) || { title: "", content: "" };
  el.onclick = null;
  el.classList.add("editing");
  el.innerHTML = `
    <div class="plan-ed">
      <div class="plan-ed-h">${n}화 계획</div>
      <input class="pe-title" placeholder="이 화 제목">
      <textarea class="pe-content" rows="3" placeholder="이 화의 핵심 사건 — 누가 무엇을 하고 무엇이 바뀌는지"></textarea>
      <div class="row2"><button class="primary pe-save">저장</button><button class="pe-cancel">취소</button></div>
    </div>`;
  el.querySelector(".pe-title").value = o.title || "";
  el.querySelector(".pe-content").value = o.content || "";
  el.querySelector(".pe-cancel").onclick = () => redraw();
  el.querySelector(".pe-save").onclick = async () => {
    const title = el.querySelector(".pe-title").value.trim();
    const content = el.querySelector(".pe-content").value.trim();
    const list = (WORK.outline || []).filter((x) => x.no !== n);
    if (title || content) list.push({ no: n, title, content });
    list.sort((a, b) => a.no - b.no);
    const r = await api(`/api/writer/works/${WORK.id}/outline`, {
      method: "PUT", body: JSON.stringify({ outline: list }),
    });
    if (!r.ok) { notice(r.error || "저장 실패"); return; }
    WORK.outline = list;
    redraw();
  };
}

function renderBible() {
  $("#bible-title").value = WORK.title || "";
  $("#bible-ending").value = WORK.ending || "";
  $("#bible-total").value = WORK.total_chapters || 25;
  const bs = $("#brief-section");
  if (WORK.brief) {
    bs.classList.remove("hidden");
    renderBriefView();
  } else {
    bs.classList.add("hidden");
  }
  renderCanon();
  const box = $("#bible-chars");
  box.innerHTML = "";
  WORK.characters.forEach((c, idx) => {
    const el = document.createElement("div");
    el.className = "b-char";
    el.innerHTML = `
      <button class="edit-ch" title="인물 수정" aria-label="${escapeHtml(c.name || "인물")} 수정">${ICO.edit}</button>
      <b>${escapeHtml(c.name || "")}</b><span class="arch">${escapeHtml(c.archetype || "")}</span>
      <p>${escapeHtml(c.role || "")}<br>욕망 — ${escapeHtml(c.want || "")} · 결핍 — ${escapeHtml(c.need || "")}<br>비밀 — ${escapeHtml(c.secret || "")}</p>`;
    el.querySelector(".edit-ch").onclick = () => editChar(el, idx);
    box.appendChild(el);
  });
  renderBibleOutline();
  $("#bible-rels").innerHTML = WORK.relations.map((r) => `
    <div class="b-rel"><b>${r.a} ↔ ${r.b}</b> · ${r.type || ""} — ${r.tension || ""}</div>`).join("");
  renderRelGraph();
  const written = WORK.chapters.length;
  $("#bible-beats").innerHTML = WORK.beats.map((b, i) => {
    const lastBeat = written ? WORK.chapters[written - 1].beat_idx : -1;
    return `<div class="b-beat ${i <= lastBeat ? "done" : ""}">
      <span class="no">${i + 1}</span><b>${b.name}</b><span>${b.summary || ""}</span></div>`;
  }).join("");
}

/* 작품 설명서 — 중복 원문 입력칸 없이, 접이식 항목 안에서 바로 편집한다. */
function briefParts(txt) {
  return String(txt || "").split(/\n(?=##\s)/).map((block) => {
    const m = block.match(/^##\s*([^\n]+)/);
    return {
      hasHeading: !!m,
      heading: m ? m[1].trim() : "작품 요약",
      body: (m ? block.slice(m[0].length) : block).trim(),
    };
  }).filter((part) => part.heading || part.body);
}

function briefText(parts) {
  return parts.map((part) => part.hasHeading
    ? `## ${part.heading}\n${part.body}`.trim()
    : part.body.trim()).filter(Boolean).join("\n\n");
}

function renderBriefView(openIndex = -1) {
  const box = $("#brief-view");
  if (!box) return;
  const parts = briefParts(WORK.brief);
  box.innerHTML = parts.map((part, idx) => `
    <details class="bv" data-brief-index="${idx}"${idx === openIndex ? " open" : ""}>
      <summary><span>${escapeHtml(part.heading)}</span>
        <button class="brief-edit-btn" title="${escapeHtml(part.heading)} 수정" aria-label="${escapeHtml(part.heading)} 수정">${ICO.edit}</button>
      </summary>
      <div class="bv-body">${escapeHtml(part.body || "내용을 입력해 주세요.").replace(/\n/g, "<br>")}</div>
    </details>`).join("");
  box.querySelectorAll(".brief-edit-btn").forEach((btn) => {
    btn.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      editBriefSection(Number(btn.closest(".bv").dataset.briefIndex));
    };
  });
}

function editBriefSection(index) {
  const parts = briefParts(WORK.brief);
  const part = parts[index];
  const card = $("#brief-view").querySelector(`.bv[data-brief-index="${index}"]`);
  if (!part || !card) return;
  card.open = true;
  card.classList.add("editing");
  card.querySelector(".brief-edit-btn").classList.add("hidden");
  card.querySelector(".bv-body").innerHTML = `
    <div class="brief-inline-edit">
      ${part.hasHeading ? '<input class="bie-heading" placeholder="항목 이름">' : ""}
      <textarea class="bie-body" rows="7" placeholder="이 설정의 내용을 적어주세요."></textarea>
      <div class="row2"><button class="primary bie-save">저장</button><button class="bie-cancel">취소</button></div>
    </div>`;
  if (part.hasHeading) card.querySelector(".bie-heading").value = part.heading;
  card.querySelector(".bie-body").value = part.body;
  card.querySelector(".bie-cancel").onclick = () => renderBriefView(index);
  card.querySelector(".bie-save").onclick = async () => {
    if (part.hasHeading) part.heading = card.querySelector(".bie-heading").value.trim() || part.heading;
    part.body = card.querySelector(".bie-body").value.trim();
    const brief = briefText(parts);
    const r = await api(`/api/writer/works/${WORK.id}/brief`, {
      method: "PUT", body: JSON.stringify({ brief }),
    });
    if (!r.ok) { notice(r.error || "저장하지 못했어요."); return; }
    WORK.brief = brief;
    renderBriefView(index);
    notice("작품 설정을 저장했어요. 다음 집필부터 반영됩니다.");
  };
}

/* ---------- 인물 관계도 (시각화) ---------- */
const RL_ESC = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
function archColor(a = "") {
  if (a.includes("영웅") || a.includes("주인공")) return "#7a5cf0";
  if (a.includes("그림자") || a.includes("적")) return "#d64b43";
  if (a.includes("멘토") || a.includes("스승")) return "#3f8ae0";
  if (a.includes("애정") || a.includes("연인") || a.includes("로맨스")) return "#d9559b";
  if (a.includes("조력")) return "#2fa07f";
  return "#6b6ae0";
}

function renderRelGraph() {
  const box = $("#rel-graph");
  const hint = $("#rel-graph-hint");
  const chars = WORK.characters || [];
  const rels = WORK.relations || [];
  if (!chars.length) { box.innerHTML = ""; box.classList.add("hidden"); if (hint) hint.classList.add("hidden"); return; }
  box.classList.remove("hidden"); if (hint) hint.classList.toggle("hidden", !rels.length);

  // 노드 = 인물 + (관계에만 등장하는 이름도 빠뜨리지 않는다)
  const nodes = chars.map((c) => ({ name: c.name, arch: c.archetype || "" }));
  const known = new Set(nodes.map((n) => n.name));
  rels.forEach((r) => [r.a, r.b].forEach((nm) => {
    if (nm && !known.has(nm)) { known.add(nm); nodes.push({ name: nm, arch: "" }); }
  }));

  const N = nodes.length;
  const W = 380, cx = W / 2, cy = W / 2, R = N <= 1 ? 0 : Math.min(120, 66 + N * 8);
  const pos = {};
  nodes.forEach((n, i) => {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / N;
    pos[n.name] = { x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) };
  });

  let edges = "";
  rels.forEach((r, i) => {
    const a = pos[r.a], b = pos[r.b];
    if (!a || !b) return;
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    edges += `<line class="rl-edge" data-rel="${i}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`;
    const label = (r.type || "").slice(0, 8);
    if (label) {
      const w = label.length * 12 + 12;
      edges += `<g class="rl-elabel" data-rel="${i}">
        <rect x="${mx - w / 2}" y="${my - 10}" width="${w}" height="20" rx="6"/>
        <text x="${mx}" y="${my + 4}">${RL_ESC(label)}</text></g>`;
    }
  });

  let nodeSvg = "";
  nodes.forEach((n) => {
    const p = pos[n.name];
    const w = Math.max(48, [...n.name].length * 15 + 20);
    nodeSvg += `<g class="rl-node" data-name="${encodeURIComponent(n.name)}" transform="translate(${p.x},${p.y})">
      <rect x="${-w / 2}" y="-15" width="${w}" height="30" rx="15" fill="${archColor(n.arch)}"/>
      <text x="0" y="5">${RL_ESC(n.name)}</text></g>`;
  });

  box.innerHTML = `<svg viewBox="0 0 ${W} ${W}" class="rl-svg"><g>${edges}</g>${nodeSvg}</svg>`;
  const svg = box.querySelector("svg");

  const clear = () => svg.querySelectorAll(".rl-node,.rl-edge,.rl-elabel")
    .forEach((e) => e.classList.remove("on", "dim"));
  svg.querySelectorAll(".rl-node").forEach((g) => {
    g.onclick = () => {
      const name = decodeURIComponent(g.dataset.name);
      if (g.classList.contains("on")) { clear(); return; }
      clear();
      const neigh = new Set([name]);
      rels.forEach((r) => { if (r.a === name) neigh.add(r.b); if (r.b === name) neigh.add(r.a); });
      svg.querySelectorAll(".rl-edge,.rl-elabel").forEach((e) => {
        const r = rels[+e.dataset.rel];
        const hit = r && (r.a === name || r.b === name);
        e.classList.add(hit ? "on" : "dim");
      });
      svg.querySelectorAll(".rl-node").forEach((nn) => {
        const nm = decodeURIComponent(nn.dataset.name);
        nn.classList.add(nm === name ? "on" : (neigh.has(nm) ? "" : "dim"));
      });
    };
  });
  svg.querySelectorAll(".rl-elabel").forEach((g) => {
    g.onclick = (ev) => {
      ev.stopPropagation();
      const r = rels[+g.dataset.rel];
      notice(`${r.a} ↔ ${r.b}\n\n${r.type || "관계"}${r.tension ? "\n— " + r.tension : ""}`);
    };
  });
}

/* ---------- 고유명사 사전 (정전) ---------- */
function renderCanon() {
  const box = $("#canon-list");
  const canon = WORK.canon || {};
  const keys = Object.keys(canon);
  if (!keys.length) {
    box.innerHTML = `<p class="hint" style="opacity:.7">아직 남겨둔 내용이 없어요.</p>`;
    return;
  }
  box.innerHTML = "";
  keys.forEach((k) => {
    const row = document.createElement("div");
    row.className = "canon-row";
    row.innerHTML = `<span class="cn-t"><b>${escapeHtml(k)}</b>${canon[k] ? ` — ${escapeHtml(canon[k])}` : ""}</span>
      <button class="del" title="삭제">✕</button>`;
    row.querySelector(".del").onclick = async () => {
      if (!await askAction(`'${k}' 항목을 삭제할까요?`, "삭제", "취소")) return;
      const r = await api(`/api/writer/works/${WORK.id}/canon/${encodeURIComponent(k)}`, { method: "DELETE" });
      if (!r || !r.ok) { notice((r && r.error) || "삭제하지 못했어요."); return; }
      delete WORK.canon[k];
      renderCanon();
    };
    box.appendChild(row);
  });
}
$("#canon-add").onclick = async () => {
  const name = $("#canon-name").value.trim();
  if (!name) { notice("고정할 이름을 입력해 주세요."); return; }
  const r = await api(`/api/writer/works/${WORK.id}/canon`, {
    method: "POST",
    body: JSON.stringify({ name, value: $("#canon-value").value.trim() }),
  });
  if (!r.ok) { notice(r.error); return; }
  WORK.canon = r.canon;
  $("#canon-name").value = ""; $("#canon-value").value = "";
  renderCanon();
  notice("고정했어요. 다음 회차부터 이 이름 그대로 씁니다.");
};

/* ---------- 설정집 편집 ---------- */
function editChar(el, idx) {
  const c = WORK.characters[idx];
  el.innerHTML = `
    <div class="form">
      <div class="row2">
        <input id="ec-name" value="${c.name || ""}" placeholder="이름">
        <input id="ec-arch" value="${c.archetype || ""}" placeholder="원형">
      </div>
      <input id="ec-role" value="${c.role || ""}" placeholder="소개">
      <div class="row2">
        <input id="ec-want" value="${c.want || ""}" placeholder="외적 욕망">
        <input id="ec-need" value="${c.need || ""}" placeholder="내적 결핍">
      </div>
      <input id="ec-secret" value="${c.secret || ""}" placeholder="비밀">
      <div class="row2">
        <button class="primary" id="ec-save">저장</button>
        <button id="ec-cancel">취소</button>
      </div>
    </div>`;
  el.querySelector("#ec-cancel").onclick = () => renderBible();
  el.querySelector("#ec-save").onclick = async () => {
    const oldName = c.name;
    Object.assign(c, {
      name: el.querySelector("#ec-name").value.trim(),
      archetype: el.querySelector("#ec-arch").value.trim(),
      role: el.querySelector("#ec-role").value.trim(),
      want: el.querySelector("#ec-want").value.trim(),
      need: el.querySelector("#ec-need").value.trim(),
      secret: el.querySelector("#ec-secret").value.trim(),
    });
    if (oldName && c.name && oldName !== c.name) {
      // 이름이 바뀌면 관계도 속 이름도 따라간다
      WORK.relations.forEach((r) => {
        if (r.a === oldName) r.a = c.name;
        if (r.b === oldName) r.b = c.name;
      });
    }
    await saveBible();
    renderBible();
  };
}

async function saveBible() {
  const total = Number($("#bible-total").value) || WORK.total_chapters || 25;
  const r = await api(`/api/writer/works/${WORK.id}/bible`, {
    method: "PUT",
    body: JSON.stringify({
      title: $("#bible-title").value.trim(),
      ending: $("#bible-ending").value.trim(),
      characters: WORK.characters, relations: WORK.relations, beats: WORK.beats,
      total_chapters: total,
    }),
  });
  if (!r.ok) { notice(r.error || "저장 실패"); return; }
  WORK.title = $("#bible-title").value.trim(); $("#wk-title").textContent = WORK.title;
  WORK.ending = $("#bible-ending").value.trim();
  WORK.total_chapters = total;
  $("#wk-progress").textContent = `${WORK.chapters.length}/${total}화`;
}
$("#bible-save-core").onclick = async () => {
  await saveBible();
  renderChapters();  // 총 회차 바뀌면 예정 회차 목록도 갱신
  notice("저장했어요. 이후 회차부터 반영됩니다.");
};

$("#wk-home").onclick = () => showHome();
$("#wk-menu").onclick = () => openMenu("work");

/* ---------- 회차별 줄거리 보기 ---------- */
$("#btn-plot").onclick = () => showPlot();

/* ══════════ 새 작품 — 단계별 설계 (위저드) ══════════
   아이디어 한 줄만 받고, 세계관·인물·플롯은 AI가 만든다.
   사용자는 확인하고 마음에 안 드는 부분만 다시 만든다. */
const WZ_TOTALS = [15, 25, 40, 70];
const WZ_OTHER = "기타 (직접 입력)";
let WZ = null;

/* ── 설정 중이던 내용은 기기에 자동 저장한다 ──────────────────────────────
   화면을 당겨 새로고침하거나, 폰이 앱을 잠시 껐다 켜도 고르던 게 날아가면 안 된다.
   페이지는 새로 뜨더라도 여기서 그대로 복구해 같은 단계로 돌려놓는다. */
const WZ_KEY = "thelife_wizard";
function wzSave() {
  if (!WZ || WZ.phase === "gen") return;              // 생성 중인 상태는 저장하지 않는다
  try {
    const { paints, ...keep } = WZ;                   // 함수는 저장할 수 없다
    localStorage.setItem(WZ_KEY, JSON.stringify({ at: Date.now(), wz: keep }));
  } catch (e) { /* 저장 공간이 없으면 조용히 넘어간다 */ }
}
function wzSaved() {
  try {
    const d = JSON.parse(localStorage.getItem(WZ_KEY) || "null");
    if (d && d.wz && typeof d.wz.i === "number" && d.wz.phase) return d.wz;
  } catch (e) { /* 깨진 값은 없는 셈 친다 */ }
  return null;
}
function wzClear() { try { localStorage.removeItem(WZ_KEY); } catch (e) {} }
/* 글자를 칠 때마다 쓰지 않고 잠깐 모았다 저장한다 */
let WZ_T = null;
function wzSaveSoon() { clearTimeout(WZ_T); WZ_T = setTimeout(wzSave, 400); }
/* 새로고침·앱 전환 직전에도 한 번 더 붙잡아 둔다 */
window.addEventListener("pagehide", wzSave);
window.addEventListener("beforeunload", wzSave);
document.addEventListener("visibilitychange", () => { if (document.hidden) wzSave(); });

function wzOpen(wz) {
  WZ = Object.assign({ i: 0, phase: "form", total: 25, sel: {}, other: {}, detail: {},
                       basic: {}, cast: [], castOpen: -1, draft: null, outline: [] }, wz || {});
  WZ.paints = {};
  WZ.live = true;                    // 지금 설정 중 → 새로고침하면 이 자리로 돌아온다
  view("w-wizard");
  if (WZ.phase === "result") { renderWzResult(); wzGo("result"); }
  else if (WZ.phase === "plan") { wzGo("plan"); }
  else if (WZ.phase === "outline") { renderWzOutline(); wzGo("outline"); }
  else { WZ.phase = "form"; wzRender(); }
}
async function startWizard() {
  const prev = wzSaved();
  if (prev) {
    const step = (prev.phase === "form") ? `${Math.min(prev.i + 1, WZ_SPEC.length)}단계` : "확인 단계";
    if (await askAction(`설정하던 작품이 있어요 (${step}).\n이어서 하시겠어요?`, "이어서 하기", "새로 시작")) {
      wzOpen(prev); return;
    }
    wzClear();
  }
  wzOpen(null);
  wzSave();
}
/* 지금까지 고른 것을 사람이 읽는 문장으로 (AI 추천의 참고 자료) */
function wzContext() {
  const b = WZ.basic;
  const bits = [];
  if (b.title) bits.push(`제목: ${b.title}`);
  if (b.logline) bits.push(`로그라인: ${b.logline}`);
  if (b.ending) bits.push(`결말: ${b.ending}`);
  WZ_SPEC.forEach((s) => {
    const v = wzValues(s.id);
    if (v.length) bits.push(`${s.title}: ${v.join(", ")}`);
  });
  return bits.join("\n");
}
function wzValues(id) {
  const arr = (WZ.sel[id] || []).slice();
  if (WZ.other[id]) arr.push(WZ.other[id]);
  return arr;
}
/* ── 단계 이동 ── */
function wzStepCount() { return WZ_SPEC.length; }
function wzRender() {
  if (WZ.phase !== "form") return;
  const s = WZ_SPEC[WZ.i];
  $("#wzp-1").classList.remove("hidden");
  ["wzp-2", "wzp-3", "wzp-4"].forEach((v) => $(`#${v}`).classList.add("hidden"));
  $("#wz-kicker").textContent = (s.group ? s.group + " · " : "") +
    (s.n ? `${s.n}번` : "기본");
  $("#wz-title").textContent = s.title;
  const sub = s.sub || (s.kind ? "" : (s.pick === 0 ? "여러 개 고를 수 있어요."
    : s.pick > 1 ? `최대 ${s.pick}개까지 고를 수 있어요.` : "하나만 고르세요."));
  $("#wz-sub").textContent = sub;
  $("#wz-sub").classList.remove("cast-summary");
  $("#wz-sub").classList.toggle("hidden", !sub);
  // 진행 표시 (전체 단계 대비)
  const stageOf = (x) => x.kind === "text" ? 1 : x.kind === "cast" ? 3
    : x.group === "스토리 방식" ? 4 : 2;
  const stage = stageOf(s);
  const peers = WZ_SPEC.filter((x) => stageOf(x) === stage);
  const within = peers.indexOf(s) + 1;
  document.querySelectorAll("#w-wizard .wz-steps > span").forEach((d) =>
    d.classList.toggle("on", +d.dataset.s <= stage));
  $("#wz-count").textContent = `${within}/${peers.length}`;
  $("#wz-kicker").textContent = ["작품의 뼈대", "분위기와 문체", "등장인물", "이야기 구조"][stage - 1];
  const box = $("#wz-step-body");
  box.innerHTML = "";
  WZ.paints = {};                     // 지운 화면의 옛 갱신함수는 버린다
  if (s.kind === "text") wzRenderText(box, s);
  else if (s.kind === "cast") wzRenderCast(box, s);
  else wzRenderPick(box, s, WZ.sel, WZ.other, WZ.detail, s.id);
  // 인물 상세 화면은 자기 하단 버튼을 직접 만든다 (덮어쓰지 않는다)
  if (!(s.kind === "cast" && WZ.castOpen >= 0)) wzFoot(s);
  wzSave();
  window.scrollTo(0, 0);
}
/* 아래 고정 버튼이 내용 마지막 줄을 가리지 않게, 버튼 높이를 재서 여백을 잡는다.
   버튼 수가 단계마다 달라지므로 숫자를 박아두면 언젠가 또 잘린다. */
function wzPad() {
  const foot = $("#wz-foot"), w = $("#w-wizard");
  if (!foot || !w) return;
  requestAnimationFrame(() => { w.style.paddingBottom = (foot.offsetHeight + 28) + "px"; });
}
window.addEventListener("resize", wzPad);

/* 하단 버튼은 어느 화면에서나 같은 모양이다 — [← 이전][다음 →] 한 줄, 그 아래 AI 보조 한 줄. */
function wzBar(prevFn, nextLabel, nextFn, ai) {
  const foot = $("#wz-foot");
  foot.innerHTML = "";
  if (ai) {
    const b = document.createElement("button");
    b.className = "btn-ghost2"; b.textContent = ai.label; b.onclick = ai.fn;
    foot.appendChild(b);
    if (ai.hint) {
      const h = document.createElement("p");
      h.className = "wz-foot-hint"; h.textContent = ai.hint;
      foot.appendChild(h);
    }
  }
  const row = document.createElement("div");
  row.className = "wz-row";
  const prev = document.createElement("button");
  prev.className = "btn-prev"; prev.textContent = "‹";
  prev.setAttribute("aria-label", "이전");
  prev.onclick = prevFn || (() => wzBackStep());
  const next = document.createElement("button");
  next.className = "btn-main"; next.textContent = nextLabel.replace(/\s*→$/, "");
  next.onclick = nextFn;
  row.appendChild(prev); row.appendChild(next);
  foot.appendChild(row);
  wzPad();
}

function renderBibleOutline() {
  const box = $("#bible-outline");
  if (!box) return;
  box.innerHTML = "";
  const outline = [...(WORK.outline || [])].sort((a, b) => Number(a.no) - Number(b.no));
  if (!outline.length) {
    box.innerHTML = '<p class="hint bible-outline-empty">아직 만들어진 회차별 줄거리가 없어요.</p>';
    return;
  }
  outline.forEach((o) => {
    const no = Number(o.no);
    const el = document.createElement("div");
    el.className = "b-outline";
    el.innerHTML = `
      <button class="edit-ch" title="${no}화 줄거리 수정" aria-label="${no}화 줄거리 수정">${ICO.edit}</button>
      <span class="b-outline-no">${no}화</span>
      <b>${escapeHtml(o.title || `${no}화`)}</b>
      <p>${escapeHtml(o.content || "아직 줄거리가 없어요.")}</p>`;
    el.querySelector(".edit-ch").onclick = () => editOutline(no, el, renderBible);
    box.appendChild(el);
  });
}
function wzFoot(s) {
  const last = WZ.i >= wzStepCount() - 1;
  let ai = null;
  if (s.kind === "text") {
    ai = { label: "AI로 나머지 채우기", fn: wzAutoAll,
           hint: "장르부터 인물·플롯까지 AI가 정합니다. 만든 뒤에 하나씩 고칠 수 있어요." };
  } else if (s.kind === "cast") {
    ai = { label: "AI로 모든 인물 만들기", fn: wzCastAll };
  } else if (s.opts) {
    ai = { label: `AI로 ${s.title} 고르기`, fn: () => wzSuggest(s) };
  }
  wzBar(null, last ? "이대로 만들기" : "다음 →",
        () => { if (last) wzGenerate(); else { WZ.i++; wzRender(); } }, ai);
}
/* 한 단계 뒤로 (하단 '이전'과 안드로이드 뒤로가기가 같이 쓴다) */
function wzBackStep() {
  if (!WZ) { showHome(); return; }
  if (WZ.phase === "outline") { wzGo("plan"); return; }
  if (WZ.phase === "plan") { wzGo("result"); return; }
  if (WZ.phase === "result") { WZ.phase = "form"; wzRender(); return; }
  if (WZ.castOpen >= 0) { WZ.castOpen = -1; wzRender(); return; }
  if (WZ.i > 0) { WZ.i--; wzRender(); return; }
  WZ.live = false; wzSave(); WZ = null;
  showHome();
}
/* 주인공부터 요금제에서 제공하는 인원수까지 한 번에 만든다 */
async function wzCastAll() {
  const hasCast = WZ.cast.some((c) => (c.name || "").trim() ||
    Object.values(c.sel || {}).some((values) => Array.isArray(values) && values.length) ||
    Object.values(c.other || {}).some((value) => String(value || "").trim()));
  if (hasCast && !await askAction("현재 인물 설정을 AI가 만든 인물진으로 바꿀까요?", "모든 인물 만들기", "취소")) return;
  const specs = WZ_CAST_SPEC.map((cs) => ({ id: cs.id, question: cs.title,
    options: (cs.opts || []).map((o) => typeof o === "string" ? o : o.v),
    pick: cs.pick === 0 ? 3 : (cs.pick || 1) }));
  busy("주인공과 등장인물을 만드는 중…");
  const r = await api("/api/writer/brief/cast-fill", { method: "POST",
    body: JSON.stringify({ context: wzContext(), create_all: true, specs }) });
  unbusy();
  if (!r.ok) {
    notice((r.error || "인물 설정을 채우지 못했어요.") + (r.detail ? `\n\n${r.detail}` : ""));
    return;
  }
  const made = (r.characters || []).filter((row) => row && row.name).map((row) => ({
    name: row.name, age: row.age || "", description: row.description || "",
    sel: row.fields || {}, other: {}, detail: {},
  }));
  if (!made.length) { notice("인물을 만들지 못했어요. 다시 시도해 주세요."); return; }
  WZ.cast = made;
  WZ.castOpen = -1;
  wzSave();
  wzRender();
}
/* 남은 단계를 건너뛰고 바로 만든다 — 고른 게 있으면 그대로 살려서 쓴다 */
function wzAutoAll() {
  if (!(WZ.basic.logline || "").trim()) {
    notice("한 줄 줄거리(로그라인)만 알려주세요.\n나머지는 AI가 정합니다.");
    return;
  }
  wzGenerate();          // 실패하면 지금 단계로 그대로 돌아온다 (WZ.i는 건드리지 않는다)
}
/* ── 기본 정보 (직접 입력) ── */
function wzRenderText(box, s) {
  s.fields.forEach((f) => {
    const wrap = document.createElement("div");
    wrap.innerHTML = `<div class="wz-label">${f.label}</div>` +
      (f.area ? `<textarea class="wz-in" rows="3" placeholder="${f.ph}"></textarea>`
               : `<input class="wz-in one" placeholder="${f.ph}">`);
    const el = wrap.querySelector("textarea,input");
    el.value = WZ.basic[f.k] || "";
    el.oninput = () => { WZ.basic[f.k] = el.value; wzSaveSoon(); };
    box.appendChild(wrap);
  });
  const t = document.createElement("div");
  t.innerHTML = `<div class="wz-label">총 회차</div><div class="chips" id="wz-totals"></div>`;
  box.appendChild(t);
  const tc = t.querySelector("#wz-totals");
  const tb = [];
  WZ_TOTALS.forEach((n) => {
    const b = document.createElement("button");
    b.className = "chip" + (WZ.total === n ? " on" : "");
    b.textContent = `${n}화`;
    // 그 자리에서 표시만 바꾼다 (다시 그리면 스크롤이 위로 튄다)
    b.onclick = () => {
      WZ.total = n;
      tb.forEach((x) => x.el.classList.toggle("on", x.n === n));
      updateLimitHelp();
      wzSave();
    };
    tb.push({ el: b, n });
    tc.appendChild(b);
  });
  const cap = (LIMITS && LIMITS.max_chapters) || 0;
  const help = document.createElement("p");
  help.className = "wz-limit-help";
  const updateLimitHelp = () => {
    help.innerHTML = WZ.total > cap
      ? `현재 <b>${escapeHtml(LIMITS.label)}</b> 플랜은 AI 회차 설계를 <b>${cap}화까지</b> 제공합니다. 나머지 회차는 직접 설계할 수 있어요.`
      : `현재 플랜에서 ${WZ.total}화까지 AI 회차 설계를 이용할 수 있어요.`;
  };
  updateLimitHelp();
  t.appendChild(help);
}
/* ── 보기 고르기 (칩 또는 설명 카드) ── */
function wzRenderPick(box, s, sel, other, detail, key) {
  const rich = (s.opts || []).some((o) => typeof o === "object");
  const cur = sel[key] || (sel[key] = []);
  const wrap = document.createElement("div");
  wrap.className = rich ? "opt-cards" : "chips";
  const btns = [];
  let detailBox = null;
  /* 고른 표시만 그 자리에서 바꾼다 — 화면을 다시 그리지 않으므로 스크롤이 튀지 않는다 */
  const paint = () => {
    const cur = sel[key] || [];
    btns.forEach((b) => b.el.classList.toggle("on", cur.includes(b.v)));
    if (otEl) {
      otEl.classList.toggle("on", !!other[key]);
      const lab = other[key] ? `기타: ${other[key]}` : WZ_OTHER;
      otEl.innerHTML = rich ? `<b>${escapeHtml(lab)}</b>` : escapeHtml(lab);
    }
    if (detailBox) detailBox.classList.toggle("hidden", !(cur.length || other[key]));
  };
  (s.opts || []).forEach((raw) => {
    const o = (typeof raw === "string") ? { v: raw } : raw;
    const el = document.createElement("button");
    el.className = rich ? "optc" : "chip";
    el.innerHTML = rich
      ? `<b>${escapeHtml(o.v)}</b>${o.h ? `<i>${escapeHtml(o.h)}</i>` : ""}
         ${o.d ? `<p>${escapeHtml(o.d)}</p>` : ""}${o.e ? `<small>${escapeHtml(o.e)}</small>` : ""}`
      : escapeHtml(o.v);
    el.onclick = () => { wzToggle(sel, key, o.v, s.pick); paint(); };
    btns.push({ el, v: o.v });
    wrap.appendChild(el);
  });
  // 기타 → 직접 입력
  const otEl = document.createElement("button");
  otEl.className = rich ? "optc" : "chip";
  otEl.onclick = () => {
    const v = prompt("직접 입력해 주세요.", other[key] || "");
    if (v === null) return;
    other[key] = v.trim();
    paint();
    wzSave();
  };
  wrap.appendChild(otEl);
  box.appendChild(wrap);
  // 고른 뒤 세부 입력 (미리 만들어 두고 보이기만 전환 — 위치가 흔들리지 않게)
  if (s.detail) {
    detailBox = document.createElement("div");
    detailBox.innerHTML = `<div class="wz-label">조금 더 자세히 (선택)</div>
      <input class="wz-in one" placeholder="${escapeHtml(s.detail)}">`;
    const el = detailBox.querySelector("input");
    el.value = detail[key] || "";
    el.oninput = () => { detail[key] = el.value; wzSaveSoon(); };
    box.appendChild(detailBox);
  }
  paint();
  WZ.paints[key] = paint;             // AI 추천 뒤 '표시만' 갱신할 때 쓴다
  return paint;
}
function wzToggle(sel, key, val, pick) {
  setTimeout(wzSave, 0);                  // 고른 뒤 상태를 바로 기기에 남긴다
  const arr = sel[key] || (sel[key] = []);
  const at = arr.indexOf(val);
  if (at >= 0) { arr.splice(at, 1); return; }
  if (pick === 1) { arr.length = 0; arr.push(val); return; }   // 하나만 (배열은 그대로 두고 내용만 바꾼다)
  if (pick > 1 && arr.length >= pick) arr.shift();   // 최대 개수 넘으면 오래된 것 밀어내기
  arr.push(val);
}
/* ── AI에게 추천받기 ── */
async function wzSuggest(s, target, quiet) {
  const opts = (s.opts || []).map((o) => (typeof o === "string" ? o : o.v));
  if (!quiet) busy("AI가 고르는 중…");
  const r = await api("/api/writer/brief/suggest", {
    method: "POST",
    body: JSON.stringify({ question: s.title, options: opts,
      pick: s.pick === 0 ? 3 : (s.pick || 1), context: wzContext() }),
  });
  if (!quiet) unbusy();
  if (!r.ok) {
    const message = (r.error || "추천을 받지 못했어요.") + (r.detail ? `\n\n${r.detail}` : "");
    if (!quiet) notice(message);
    return { ok: false, error: message };
  }
  (target || WZ.sel)[s.id] = r.picked;
  wzSave();
  if (quiet) return { ok: true, demo: !!r.demo };
  // 표시만 그 자리에서 갱신 (화면을 다시 그리지 않아 보던 위치가 유지된다)
  if (WZ.paints[s.id]) WZ.paints[s.id]();
  else if (target) wzRenderCastDetail(); else wzRender();
  if (r.reason) notice(`AI 추천: ${r.picked.join(", ")}\n\n${r.reason}`);
  return { ok: true, demo: !!r.demo };
}

/* ── 인물 설정 ── */
function wzRenderCast(box, s) {
  if (WZ.castOpen >= 0) { wzRenderCastDetail(box); return; }
  const list = document.createElement("div");
  list.className = "cast-list";
  WZ.cast.forEach((c, i) => {
    const el = document.createElement("div");
    el.className = "cast-row";
    const done = WZ_CAST_SPEC.filter((cs) => (c.sel[cs.id] || []).length || c.other[cs.id]).length;
    el.innerHTML = `<div class="cast-main">
        <div class="cast-name-row"><b class="cast-nm">${escapeHtml(c.name || "새 인물")}</b>
          <span class="cast-done">${done} / ${WZ_CAST_SPEC.length}</span></div>
        <span class="cast-meta">${escapeHtml([c.age, wzCastRole(c)].filter(Boolean).join(" · ") || "이름과 역할을 정해 주세요")}</span>
      </div>
      <button class="cast-more">설정</button>
      <button class="cast-del" title="삭제" aria-label="인물 삭제">✕</button>`;
    el.querySelector(".cast-more").onclick = () => { WZ.castOpen = i; wzRender(); };
    el.querySelector(".cast-del").onclick = async () => {
      if (!await askAction(c.name ? `'${c.name}' 인물을 삭제할까요?` : "이 인물을 삭제할까요?", "삭제", "취소")) return;
      WZ.cast.splice(i, 1); wzSave(); wzRender();
    };
    list.appendChild(el);
  });
  box.appendChild(list);
  const add = document.createElement("button");
  add.className = "btn-ghost2";
  add.textContent = "＋ 인물 추가";
  add.onclick = () => {
    WZ.cast.push({ name: "", age: "", sel: {}, other: {}, detail: {} });
    WZ.castOpen = WZ.cast.length - 1;
    wzRender();
  };
  box.appendChild(add);
}
/* 역할(관계)은 10번 항목에서 고른 값 */
function wzCastRole(c) {
  const k = (WZ_CAST_SPEC[0] || {}).id;
  const a = (c.sel[k] || []).slice();
  if (c.other[k]) a.push(c.other[k]);
  return a.join(", ");
}
function wzLocalCastSummary(c) {
  const pick = (id, fallback) => {
    const values = (c.sel[id] || []).slice();
    if (c.other[id]) values.push(c.other[id]);
    return values.join(", ") || fallback;
  };
  const name = (c.name || "이 인물").trim();
  const role = pick("role", "등장인물");
  const personality = pick("personality", "자신만의 성격");
  const want = pick("want", "자신의 목표");
  const fear = pick("fear", "실패");
  const secret = pick("secret", "감춰 둔 사정");
  const facade = pick("facade", "겉으로 드러나는 모습");
  const truth = pick("truth", "내면의 실제 모습");
  const title = (WZ.basic.title || "이 작품").trim();
  const logline = (WZ.basic.logline || "").trim();
  if (!(c.name || "").trim() || !wzCastRole(c)) return "";
  return `${name}, 『${title}』에서 ${role} 역할로 움직이는 캐릭터입니다. ` +
    `${logline ? `‘${logline}’라는 중심 사건 속에서 ` : "작품의 중심 사건 속에서 "}` +
    `가장 원하는 것은 ${want}이고 가장 두려운 것은 ${fear}이라 중요한 선택 앞에서 흔들립니다. ` +
    `${personality} 성향은 다른 인물과의 충돌과 뜻밖의 결정을 만듭니다. ` +
    `겉으로는 ${facade}처럼 보이지만 실제로는 ${truth}에 가깝습니다. 숨긴 비밀은 ${secret}이며, ` +
    `이 비밀이 이야기의 방향을 바꿉니다.`;
}
function wzRenderCastDetail(box) {
  box = box || $("#wz-step-body");
  box.innerHTML = "";
  WZ.paints = {};
  const c = WZ.cast[WZ.castOpen];
  if (!c) { WZ.castOpen = -1; wzRender(); return; }
  if (!c.description) {
    c.description = wzLocalCastSummary(c);
    if (c.description) wzSaveSoon();
  }
  $("#wz-kicker").textContent = "인물 설정";
  $("#wz-title").textContent = c.name || "이 인물";
  $("#wz-sub").textContent = c.description || "";
  $("#wz-sub").classList.add("cast-summary");
  $("#wz-sub").classList.toggle("hidden", !c.description);
  // 기본 정보 — 모든 인물이 먼저 갖는 것
  const basic = document.createElement("div");
  basic.className = "cast-basic";
  basic.innerHTML = `<div class="wz-label">기본 정보</div>
    <div class="row2"><input class="cb-n" placeholder="이름" value="${escapeHtml(c.name || "")}">
      <input class="cb-a" placeholder="나이" value="${escapeHtml(c.age || "")}"></div>`;
  basic.querySelector(".cb-n").oninput = (e) => {
    c.name = e.target.value; $("#wz-title").textContent = c.name || "이 인물"; wzSaveSoon();
  };
  basic.querySelector(".cb-a").oninput = (e) => { c.age = e.target.value; wzSaveSoon(); };
  box.appendChild(basic);
  WZ_CAST_SPEC.forEach((cs) => {
    const h = document.createElement("div");
    h.className = "cast-sec";
    h.innerHTML = `<div class="wz-label">${cs.n}. ${cs.title}</div>`;
    box.appendChild(h);
    wzRenderPick(box, cs, c.sel, c.other, c.detail, cs.id);
  });
  wzBar(() => { WZ.castOpen = -1; wzRender(); }, "다음 →",
        () => { WZ.castOpen = -1; wzRender(); },
        { label: "AI가 이 인물 설정하기", fn: () => wzCastOne(c) });
  window.scrollTo(0, 0);
}
/* 이 인물의 빈 항목을 한 번에 채운다 (개별 추천 버튼 대신) */
async function wzCastOne(c) {
  if (!(c.name || "").trim()) { notice("이름을 먼저 적어 주세요."); return; }
  busy("AI가 이 인물을 설정하는 중…");
  for (const cs of WZ_CAST_SPEC) await wzSuggest(cs, c.sel, true);
  unbusy();
  wzRenderCastDetail();
}
/* 선택 단계가 끝난 뒤의 화면 (생성 중 / 확인 / 회차) */
function wzGo(phase) {
  WZ.phase = phase;
  wzSave();
  const pane = { gen: "wzp-2", result: "wzp-3", plan: "wzp-5", outline: "wzp-4" }[phase];
  ["wzp-1", "wzp-2", "wzp-3", "wzp-4", "wzp-5"].forEach((v) =>
    $(`#${v}`).classList.toggle("hidden", v !== pane));
  document.querySelectorAll("#w-wizard .wz-dot").forEach((d) => d.classList.add("on"));
  $("#wz-count").textContent =
    { gen: "생성 중", result: "세계관", plan: "화별 줄거리", outline: "완성" }[phase] || "";
  const foot = $("#wz-foot");
  foot.innerHTML = "";
  if (phase === "gen") { wzPad(); return; }          // 생성 중엔 버튼 없음
  if (phase === "result") {
    wzBar(null, "다음 (화별 줄거리 짜기) →", () => { wzSaveWorld(); wzGo("plan"); },
          { label: "세계관 다시 만들기", fn: () => wzRedraw("world") });
  }
  if (phase === "plan") {
    renderWzPlan();
    wzBar(null, "다음 →", wzPlanNext,
          { label: "AI가 전체 줄거리 짜기", fn: wzOutline });
  }
  if (phase === "outline") wzBar(null, "완성! 작품 시작하기", wzFinish, null);
  window.scrollTo(0, 0);
}
/* 확인 화면에서 고친 세계관·결말을 기획에 되돌려 넣는다 */
function wzSaveWorld() {
  const d = WZ.draft || (WZ.draft = {});
  const g = (id) => { const e = $("#" + id); return e ? e.value.trim() : undefined; };
  const t = g("wzr-title"); if (t !== undefined) d.title = t;
  const w = g("wzr-world"); if (w !== undefined) d.world_setting = w;
  const r = g("wzr-rules"); if (r !== undefined) d.world_rules = r;
  const b = g("wzr-taboos"); if (b !== undefined) d.taboos = b;
  const e2 = g("wzr-ending"); if (e2 !== undefined) d.ending = e2;
  wzSave();
}
/* ── 화별 줄거리 구성 (작가가 직접 짜는 자리) ── */
function wzPlanRows() {
  const cap = (LIMITS && LIMITS.max_chapters) || WZ.total;
  return Math.max(1, Math.min(WZ.total, cap));
}
function renderWzPlan() {
  const n = wzPlanRows();
  const cap = (LIMITS && LIMITS.max_chapters) || WZ.total;
  const syn = (LIMITS && LIMITS.syn_chars) || 0;
  const label = (LIMITS && LIMITS.label) || "";
  const note = $("#wz-plan-note");
  note.innerHTML = WZ.total > cap
    ? `현재 <b>${escapeHtml(label)}</b> 요금제라 AI로 만드는 줄거리는 <b>${cap}화까지</b>예요.
       (고른 총 회차는 ${WZ.total}화) 화당 줄거리는 <b>약 ${syn}자</b>까지 자세히 써집니다.
       <button class="wz-note-go">요금제 보기</button>`
    : `<b>${escapeHtml(label)}</b> 요금제 — ${cap}화까지, 화당 약 ${syn}자까지 자세히 써집니다.`;
  const go = note.querySelector(".wz-note-go");
  if (go) go.onclick = () => showPlans();
  const box = $("#wz-plan-list");
  box.innerHTML = "";
  WZ.plan = WZ.plan || {};
  for (let i = 1; i <= n; i++) {
    const row = document.createElement("div");
    row.className = "wz-plan-row";
    const cur = WZ.plan[i] || {};
    row.innerHTML = `<span class="n">${i}화</span>
      <input class="pt" placeholder="이 화 제목 (선택)" value="${escapeHtml(cur.title || "")}">
      <textarea class="pc" rows="2" placeholder="이 화에 벌어지는 일 (비워두면 AI가 채워요)">${escapeHtml(cur.content || "")}</textarea>`;
    row.querySelector(".pt").oninput = (e) => {
      (WZ.plan[i] = WZ.plan[i] || {}).title = e.target.value; wzSaveSoon();
    };
    row.querySelector(".pc").oninput = (e) => {
      (WZ.plan[i] = WZ.plan[i] || {}).content = e.target.value; wzSaveSoon();
    };
    box.appendChild(row);
  }
}
/* 직접 채운 게 있으면 그대로 쓰고, 다 비었으면 AI에게 맡긴다 */
async function wzPlanNext() {
  const n = wzPlanRows();
  const mine = [];
  for (let i = 1; i <= n; i++) {
    const c = WZ.plan[i] || {};
    if ((c.title || "").trim() || (c.content || "").trim()) {
      mine.push({ no: i, title: (c.title || "").trim(), content: (c.content || "").trim() });
    }
  }
  if (!mine.length) { wzOutline(); return; }          // 하나도 안 채웠으면 AI가
  if (mine.length < n) {
    if (!await askAction(`${n}화 중 ${mine.length}화만 채웠어요.\n나머지는 AI가 채울까요?`, "AI로 채우기", "이대로 사용")) {
      WZ.outline = mine; renderWzOutline(); wzGo("outline"); return;
    }
    wzOutline(); return;
  }
  WZ.outline = mine;
  renderWzOutline();
  wzGo("outline");
}
/* 고른 항목들을 작품설명서 형식으로 옮긴다 */
function wzJoin(id) { return wzValues(id).join(", "); }
function wzLine(label, id) { const v = wzJoin(id); return v ? `${label}: ${v}` : ""; }
function wzCastOut() {
  const out = [];
  WZ.cast.forEach((c) => {
    if (!(c.name || "").trim()) return;
    const pick = (k) => {
      const a = (c.sel[k] || []).slice();
      if (c.other[k]) a.push(c.other[k]);
      let s = a.join(", ");
      if (c.detail[k]) s += (s ? " — " : "") + c.detail[k];
      return s;
    };
    out.push({ name: c.name.trim(), age: (c.age || "").trim(), role: pick("role"),
      personality: pick("personality"), want: pick("want"), fear: pick("fear"),
      secret: pick("secret"), facade: pick("facade"), truth: pick("truth"),
      description: c.description || "", need: "", relation: "" });
  });
  return out;
}
function wzBody(extra) {
  const d = (WZ.draft || {});
  const cast = wzCastOut();
  const lead = cast.find((c) => (c.role || "").includes("주인공"));
  const style = [wzLine("분위기", "mood"), wzLine("속도", "pace"), wzLine("감정 표현", "emotion"),
                 wzLine("대사", "dialogue"), wzLine("묘사", "describe")].filter(Boolean).join(" / ");
  const world = [wzLine("시대", "era"), wzLine("주요 배경", "place")].filter(Boolean).join("\n");
  const structure = [wzLine("시간의 흐름", "time"), wzLine("정보 전달", "info"),
                     wzLine("반전", "twist"), wzLine("플롯 유형", "plot")].filter(Boolean).join("\n");
  return Object.assign({
    title: WZ.basic.title || d.title || "",
    genre: wzJoin("genre") || d.genre || "",
    total_chapters: WZ.total,
    logline: WZ.basic.logline || d.logline || "",
    ending: WZ.basic.ending || d.ending || "",
    intent: wzLine("이야기에서 중요한 것", "focus") || d.intent || "",
    world_setting: d.world_setting || world || "",
    world_rules: d.world_rules || "", taboos: d.taboos || "",
    style: style || d.style || "",
    structure: structure,
    protagonist: (d.protagonist && d.protagonist.name) ? d.protagonist
      : (lead ? { name: lead.name, age: lead.age, personality: lead.personality,
                  want: lead.want, need: lead.fear, secret: lead.secret,
                  description: lead.description || "" } : {}),
    characters: (d.characters && d.characters.length) ? d.characters : cast,
    canon: d.canon || [],
    outline: (WZ.outline && WZ.outline.length) ? WZ.outline : wzPlanOut(),
  }, extra || {});
}
/* 작가가 화별 줄거리 화면에서 직접 채운 것 */
function wzPlanOut() {
  const out = [];
  Object.keys(WZ.plan || {}).forEach((k) => {
    const v = WZ.plan[k] || {};
    if ((v.title || "").trim() || (v.content || "").trim()) {
      out.push({ no: Number(k), title: (v.title || "").trim(), content: (v.content || "").trim() });
    }
  });
  return out.sort((a, b) => a.no - b.no);
}
function wzTasks(list) {
  $("#wz-tasks").innerHTML = list.map((t) =>
    `<div class="task ${t[1]}"><span class="ic">${t[1] === "done" ? "✓" : ""}</span>${t[0]}</div>`).join("");
}
async function wzGenerate() {
  const b = WZ.basic;
  if (!(b.logline || "").trim() && !wzJoin("genre")) {
    notice("로그라인이나 장르 중 하나는 알려주세요."); return;
  }
  wzGo("gen");
  $("#wz-gen-h").textContent = "세계관을 만들고 있어요";
  wzTasks([["배경 만드는 중", "now"], ["규칙·금기 정리", ""], ["결말 고정", ""]]);
  const r = await api("/api/writer/brief/draft", {
    method: "POST", body: JSON.stringify(wzBody()),
  });
  if (!r.ok) {
    notice((r.error || "만들지 못했어요.") + (r.detail ? `\n\n${r.detail}` : ""));
    WZ.phase = "form"; wzRender();
    return;
  }
  WZ.draft = r.draft || {};
  WZ.demo = !!r.demo;
  wzSave();
  wzTasks([["배경 만드는 중", "done"], ["규칙·금기 정리", "done"], ["결말 고정", "done"]]);
  renderWzResult();
  setTimeout(() => wzGo("result"), 350);
}
/* 일부만 다시 만들기 — 그 칸을 비우고 다시 요청하면 그 부분만 새로 생성된다 */
async function wzRedraw(field) {
  if (!WZ.draft) return;
  const keep = Object.assign({}, WZ.draft);
  if (field === "world") { keep.world_setting = ""; keep.world_rules = ""; keep.taboos = ""; }
  else if (field === "characters") { keep.characters = []; keep.protagonist = {}; }
  busy("다시 만드는 중…");
  const saved = WZ.draft; WZ.draft = keep;
  const r = await api("/api/writer/brief/draft", { method: "POST", body: JSON.stringify(wzBody()) });
  unbusy();
  if (!r.ok) { WZ.draft = saved; notice(r.error || "다시 만들지 못했어요."); return; }
  WZ.draft = r.draft || saved;
  wzSave();
  renderWzResult();
}
function renderWzResult() {
  const d = WZ.draft || {};
  const box = $("#wz-result");
  let h = WZ.demo ? `<div class="wz-demo-note">미리보기용 예시 기획입니다. 실제 앱에서는 연결된 AI가 작품 설정에 맞춰 생성합니다.</div>` : "";
  h += `<div class="wzc"><h3>제목</h3>
      <input id="wzr-title" class="wz-in one" value="${escapeHtml(d.title || "")}" placeholder="제목">
      <p class="wzc-p">${escapeHtml(d.logline || "")}</p></div>
    <div class="wzc"><h3>세계관</h3>
      <label class="wzc-l">배경</label>
      <textarea id="wzr-world" class="wz-in" rows="3">${escapeHtml(d.world_setting || "")}</textarea>
      <label class="wzc-l">핵심 규칙</label>
      <textarea id="wzr-rules" class="wz-in" rows="4">${escapeHtml(d.world_rules || "")}</textarea>
      <label class="wzc-l">금기 · 제약</label>
      <textarea id="wzr-taboos" class="wz-in" rows="2">${escapeHtml(d.taboos || "")}</textarea></div>`;
  const cast = [];
  if (d.protagonist && d.protagonist.name) cast.push(Object.assign({ role: "주인공" }, d.protagonist));
  (d.characters || []).forEach((c) => cast.push(c));
  if (cast.length) h += `<div class="wzc-h">인물 <small>앞 단계에서 정한 인물이에요</small></div>`;
  cast.forEach((c, i) => {
    const col = i === 0 ? "linear-gradient(135deg,#8b70ff,#6a54f0)"
      : ["linear-gradient(135deg,#d9559b,#c23f86)", "linear-gradient(135deg,#d64b43,#b03b34)",
         "linear-gradient(135deg,#3f8ae0,#2f7fce)", "linear-gradient(135deg,#2fa07f,#258066)"][i % 4];
    h += `<div class="wzp"><div class="wzp-av" style="background:${col}">${escapeHtml((c.name || "?").slice(0, 1))}</div>
      <div><b>${escapeHtml(c.name || "")}</b><span class="role">${escapeHtml(c.role || "")}</span>
      <p>${escapeHtml([c.relation, c.want && "욕망 " + c.want, c.need && "결핍 " + c.need,
        c.secret && "비밀 " + c.secret].filter(Boolean).join(" · "))}</p></div></div>`;
  });
  h += `<div class="wzc"><h3>결말</h3>
      <textarea id="wzr-ending" class="wz-in" rows="3">${escapeHtml(d.ending || "")}</textarea></div>`;
  box.innerHTML = h;
  box.querySelectorAll("textarea,input").forEach((el) => { el.oninput = () => wzSaveSoon(); });
}
async function wzOutline() {
  const back = WZ.phase;
  wzGo("gen");
  $("#wz-gen-h").textContent = "회차별 줄거리를 짜고 있어요";
  wzTasks([["설정 정리", "done"], [`1화~${wzPlanRows()}화 흐름 만드는 중`, "now"]]);
  const r = await api("/api/writer/brief/outline", { method: "POST", body: JSON.stringify(wzBody()) });
  if (!r.ok) {
    notice((r.error || "전개를 못 만들었어요.") + (r.detail ? `\n\n${r.detail}` : ""));
    wzGo(back === "gen" ? "plan" : back); return;
  }
  WZ.outline = r.outline || [];
  WZ.demo = !!r.demo;
  wzSave();
  renderWzOutline(r);
  wzGo("outline");
}
function renderWzOutline(r) {
  const d = WZ.draft || {};
  const rows = (WZ.outline || []).map((o) =>
    `<div class="wz-ep" data-outline-no="${Number(o.no)}">
      <button class="edit-ch" title="${Number(o.no)}화 줄거리 수정" aria-label="${Number(o.no)}화 줄거리 수정">${ICO.edit}</button>
      <span class="n">${o.no}화</span><div><b>${escapeHtml(o.title || "")}</b>
      <span>${escapeHtml(o.content || "")}</span></div></div>`).join("");
  const cap = (r && r.capped) || ((LIMITS && LIMITS.max_chapters) || WZ.total) < WZ.total;
  const lim = (LIMITS && LIMITS.max_chapters) || WZ.total;
  const demoNote = WZ.demo
    ? `<div class="wz-demo-note">미리보기용 예시 회차입니다. 실제 앱에서는 연결된 AI가 설정에 맞춰 생성합니다.</div>` : "";
  const capNote = cap
    ? `<div class="wz-note">현재 <b>${escapeHtml((LIMITS && LIMITS.label) || "")}</b> 요금제라
         AI 줄거리는 <b>${lim}화까지</b>만 만들어졌어요 (고른 총 회차 ${WZ.total}화).
         나머지 회차는 작품을 시작한 뒤 직접 채우거나, 요금제를 올리면 이어서 만들 수 있어요.</div>`
    : "";
  $("#wz-outline").innerHTML = demoNote + capNote +
    `<div class="wzc"><h3>총 ${WZ.outline.length || WZ.total}화 · 결말 고정</h3>
       <p style="color:var(--text)">${escapeHtml(d.ending || "")}</p></div>
     <div class="wz-edit-help">${ICO.edit}<span>연필 버튼을 누르면 AI가 만든 줄거리를 바로 수정할 수 있어요.</span></div>
     <div class="wzc" style="padding:6px 16px">${rows || "<p>줄거리가 비어 있어요.</p>"}</div>`;
  $("#wz-outline").querySelectorAll(".wz-ep .edit-ch").forEach((btn) => {
    btn.onclick = () => {
      const el = btn.closest(".wz-ep");
      editWzOutline(Number(el.dataset.outlineNo), el);
    };
  });
}

function editWzOutline(no, el) {
  const o = (WZ.outline || []).find((x) => Number(x.no) === no) || { title: "", content: "" };
  el.classList.add("editing");
  el.innerHTML = `
    <div class="plan-ed">
      <div class="plan-ed-h">${no}화 줄거리 수정</div>
      <input class="pe-title" placeholder="이 화 제목">
      <textarea class="pe-content" rows="5" placeholder="이 화에서 누가 무엇을 하고, 어떤 변화가 생기는지 적어주세요."></textarea>
      <div class="row2"><button class="primary pe-save">저장</button><button class="pe-cancel">취소</button></div>
    </div>`;
  el.querySelector(".pe-title").value = o.title || "";
  el.querySelector(".pe-content").value = o.content || "";
  el.querySelector(".pe-cancel").onclick = () => renderWzOutline();
  el.querySelector(".pe-save").onclick = () => {
    const title = el.querySelector(".pe-title").value.trim();
    const content = el.querySelector(".pe-content").value.trim();
    WZ.outline = (WZ.outline || []).filter((x) => Number(x.no) !== no)
      .concat([{ no, title, content }]).sort((a, b) => Number(a.no) - Number(b.no));
    wzSave();
    renderWzOutline();
  };
}
async function wzFinish() {
  busy("작품을 만드는 중…");
  const r = await api("/api/writer/works/build", { method: "POST", body: JSON.stringify(wzBody()) });
  unbusy();
  if (!r.ok) { notice((r.error || "작품을 만들지 못했어요.") + (r.detail ? `\n\n${r.detail}` : "")); return; }
  WZ = null;
  wzClear();
  await openWork(r.id);
  notice("작품이 만들어졌어요! 회차를 눌러 집필을 시작하세요.");
}
$("#wz-home").onclick = () => {
  if (WZ) { WZ.live = false; wzSave(); WZ = null; }
  showHome();
};
$("#wz-menu").onclick = () => openMenu("wizard");

/* ══════════ 회차별 줄거리 (아코디언) ══════════
   제목을 누르면 그 화의 줄거리가 펼쳐지고, 다른 제목을 누르면 접힌다. */
let PLOT_OPEN = 0;                     // 지금 펼쳐진 화 번호 (0=없음)

function showPlot(focusNo) {
  view("w-plot");
  if (focusNo) PLOT_OPEN = focusNo;
  renderPlotList();
}
function plotRows() {
  const byNo = {}, written = {};
  (WORK.outline || []).forEach((o) => { byNo[o.no] = o; });
  (WORK.chapters || []).forEach((ch) => { written[ch.no] = ch; });
  const total = Math.max(WORK.total_chapters || 0, WORK.chapters.length,
    ...(WORK.outline || []).map((o) => o.no), 0);
  const rows = [];
  for (let n = 1; n <= total; n++) rows.push({ no: n, o: byNo[n], ch: written[n] });
  return rows;
}
function renderPlotList() {
  const rows = plotRows();
  const writtenCount = (WORK.chapters || []).filter((ch) => (ch.chars || 0) > 0).length;
  $("#pl-meta").textContent = `총 ${rows.length}화 · ${writtenCount}화 집필 완료`;
  $("#pl-menu").title = "메뉴";
  const box = $("#pl-list");
  box.innerHTML = "";
  rows.forEach(({ no, o, ch }) => {
    const open = PLOT_OPEN === no;
    const title = (ch && ch.title) || (o && o.title) || `${no}화`;
    const el = document.createElement("div");
    el.className = "pl-item" + (open ? " open" : "");
    const preview = (o && o.content) || (ch && ch.summary) || "아직 줄거리가 없어요.";
    const done = ch && (ch.chars || 0) > 0;
    el.innerHTML =
      `<button class="pl-head"><span class="pl-no">${no}화</span>
         <span class="pl-copy"><span class="pl-t">${escapeHtml(title)}</span>
         <small>${escapeHtml(preview.slice(0, 72))}</small></span>
         <span class="pl-state ${done ? "done" : ""}">${done ? "집필 완료" : "미집필"}</span>
         <span class="pl-chev">${open ? "접기" : "열기"}</span></button>`;
    el.querySelector(".pl-head").onclick = () => {
      PLOT_OPEN = open ? 0 : no;       // 같은 걸 누르면 접기, 다른 걸 누르면 그것만 열기
      renderPlotList();
    };
    if (open) {
      const pane = document.createElement("div");
      pane.className = "pl-pane";
      const syn = (o && o.content) ? escapeHtml(o.content)
        : (ch && ch.summary ? escapeHtml(ch.summary) : "");
      pane.innerHTML =
        `<p class="pl-syn${syn ? "" : " empty"}">${syn || "아직 줄거리가 없어요."}</p>
         <button class="pl-edit">줄거리 고치기</button>
         <div class="pl-acts">
            <button class="smp${SAMPLE.base > 0 ? "" : " off"}">1,000자 본문 예시</button>
           <button class="go">${ch ? "이어 쓰기" : "쓰기"}</button>
         </div>`;
      pane.querySelector(".smp").onclick = () => {
        if (SAMPLE.base <= 0) { showPlans("plot"); return; }
        makeSample({ work_id: WORK.id, no, title: `${no}화 본문 예시` });
      };
      pane.querySelector(".go").onclick = () => openChapterByNo(no);
      pane.querySelector(".pl-edit").onclick = () => editPlotSyn(pane, no);
      el.appendChild(pane);
    }
    box.appendChild(el);
  });
}
/* 줄거리 직접 고치기 — AI가 쓴 것도 작가가 언제든 바꾼다 */
function editPlotSyn(pane, no) {
  const o = (WORK.outline || []).find((x) => x.no === no) || { title: "", content: "" };
  const box = pane.querySelector(".pl-syn");
  box.outerHTML = `<div class="pl-ed">
    <input class="pe-t" placeholder="이 화 제목" value="${escapeHtml(o.title || "")}">
    <textarea class="pe-c" rows="5" placeholder="이 화에 벌어지는 일">${escapeHtml(o.content || "")}</textarea>
    <div class="row2"><button class="primary pe-s">수정 내용 저장</button>
      <button class="pe-x">취소</button></div></div>`;
  pane.querySelector(".pe-x").onclick = () => renderPlotList();
  pane.querySelector(".pe-s").onclick = async () => {
    const title = pane.querySelector(".pe-t").value.trim();
    const content = pane.querySelector(".pe-c").value.trim();
    const next = (WORK.outline || []).filter((x) => x.no !== no)
      .concat([{ no, title, content }]).sort((a, b) => a.no - b.no);
    const r = await api(`/api/writer/works/${WORK.id}/outline`, {
      method: "PUT", body: JSON.stringify({ outline: next }),
    });
    if (!r.ok) { notice(r.error || "저장하지 못했어요."); return; }
    WORK.outline = r.outline || next;
    renderPlotList();
    notice("줄거리를 저장했어요.");
  };
}
$("#pl-home").onclick = () => openWork(WORK.id);
$("#pl-menu").onclick = () => openMenu("plot");

/* ══════════ 본문 쓰기 ══════════ */
let DIRTY = false, SAVING = false, DRAFT_T = null;
const draftKey = (id) => `draft:${id}`;

async function openChapter(id) {
  const d = await api(`/api/writer/chapters/${id}`);
  if (!d.ok) { notice("회차를 불러오지 못했어요"); return; }
  CHAPTER = d.chapter;
  view("w-editor");
  closeSheet();
  $("#ed-heading").textContent = `${CHAPTER.no}화 본문 쓰기`;
  $("#ed-title").value = CHAPTER.title || "";
  $("#ed-body").value = CHAPTER.body || "";
  DIRTY = false;
  // 임시저장본이 서버 내용과 다르면 되살린다 (앱이 꺼져도 글이 안 날아가게)
  try {
    const raw = localStorage.getItem(draftKey(id));
    if (raw) {
      const dr = JSON.parse(raw);
      if ((dr.body || "") !== (CHAPTER.body || "") || (dr.title || "") !== (CHAPTER.title || "")) {
        $("#ed-title").value = dr.title || "";
        $("#ed-body").value = dr.body || "";
        DIRTY = true;
        notice("저장하지 않고 종료된 글을 되살렸어요.\n확인 후 '저장하기'를 눌러주세요.");
      }
    }
  } catch (e) { /* 임시저장은 없어도 그만 */ }
  const nos = plotRows().map((r) => r.no);
  $("#ed-prev").disabled = CHAPTER.no <= Math.min(...nos, 1);
  $("#ed-next").disabled = CHAPTER.no >= Math.max(...nos, CHAPTER.no);
  edStatus();
}
/* 번호로 열기 — 아직 없는 회차면 빈 회차를 만들어서 바로 쓸 수 있게 연다 */
function openChapterByNo(no) {
  const ch = (WORK.chapters || []).find((c) => c.no === no);
  if (ch) { openChapter(ch.id); return; }
  startWriting(no);
}

$("#ed-body").addEventListener("input", onEdit);
$("#ed-title").addEventListener("input", onEdit);
function onEdit() {
  DIRTY = true;
  edStatus();
  clearTimeout(DRAFT_T);
  DRAFT_T = setTimeout(saveDraft, 700);      // 타이핑이 멈추면 자동 임시저장
}
function saveDraft() {
  if (!CHAPTER) return;
  try {
    localStorage.setItem(draftKey(CHAPTER.id), JSON.stringify({
      title: $("#ed-title").value, body: $("#ed-body").value, at: Date.now(),
    }));
    edStatus("임시저장됨");
  } catch (e) { /* 저장공간 부족 등 — 무시 */ }
}
function edStatus(msg) {
  const n = $("#ed-body").value.length.toLocaleString();
  $("#ed-status").textContent = `${n}자 · ` + (msg || (DIRTY ? "저장 안 됨" : "저장됨"));
}
async function saveChapter(quiet) {
  if (!CHAPTER || SAVING) return false;
  SAVING = true;
  const r = await api(`/api/writer/chapters/${CHAPTER.id}`, {
    method: "PUT",
    body: JSON.stringify({ title: $("#ed-title").value, body: $("#ed-body").value }),
  });
  SAVING = false;
  if (!r.ok) { notice(r.error || "저장 실패"); return false; }
  DIRTY = false;
  try { localStorage.removeItem(draftKey(CHAPTER.id)); } catch (e) {}
  // 로컬 사본도 갱신해 앞뒤 이동 시 최신 내용이 보이게
  const mine = (WORK.chapters || []).find((c) => c.id === CHAPTER.id);
  if (mine) { mine.title = $("#ed-title").value; }
  edStatus("저장됨");
  if (!quiet) edStatus("저장 완료");
  return true;
}
$("#ed-save").onclick = () => saveChapter();

/* 이동 전 저장 확인 — 저장 안 한 변경이 있으면 물어본다 */
function guard(go) {
  if (!DIRTY) { go(); return; }
  $("#confirm-text").textContent = "저장하지 않은 내용이 있어요.\n저장할까요?";
  $("#confirm").classList.remove("hidden");
  $("#cf-save").onclick = async () => {
    $("#confirm").classList.add("hidden");
    if (await saveChapter(true)) go();
  };
  $("#cf-discard").onclick = () => {
    $("#confirm").classList.add("hidden");
    DIRTY = false;
    try { localStorage.removeItem(draftKey(CHAPTER.id)); } catch (e) {}
    go();
  };
  $("#cf-cancel").onclick = () => $("#confirm").classList.add("hidden");
}
function stepChapter(delta) {
  const target = CHAPTER.no + delta;
  const total = Math.max(WORK.total_chapters || 0, ...plotRows().map((r) => r.no), 0);
  if (target < 1 || target > total) {
    notice(delta > 0 ? "마지막 회차예요." : "첫 회차예요."); return;
  }
  guard(() => openChapterByNo(target));
}
$("#ed-prev").onclick = () => stepChapter(-1);
$("#ed-next").onclick = () => stepChapter(1);
$("#ed-home").onclick = () => guard(() => openWork(WORK.id));
$("#ed-menu").onclick = () => openMenu("editor");

/* 브라우저/앱을 그냥 닫아도 글이 남도록 */
window.addEventListener("beforeunload", (e) => {
  if (!DIRTY) return;
  saveDraft();
  e.preventDefault();
  e.returnValue = "";
});

/* ══════════ 본문 예시 (설정대로 써본 한 토막, 약 1,000자) ══════════
   회차 본문이 아니라 '내 설정이 글로 나오면 어떤 느낌인지' 보는 참고용이다.
   등급별로 하루 몇 건까지, 광고를 보면 1건씩 더. */
const SAMPLE_NOTE = "이 예시는 작품을 쓰는데 도움이 되도록 설정된 내용을 반영한 본문 예시입니다. " +
  "전체적인 흐름과는 다소 차이가 날 수 있으며, 본문 작성에 참고용으로 이용 바랍니다.";
let SAMPLE = { used: 0, base: 1, extra: 0, left: 1 };
let SAMPLE_TEXT = "";

function smpLeftText() {
  const total = SAMPLE.base + SAMPLE.extra;
  return `오늘 ${total}건 중 ${SAMPLE.left}건 남음 · 광고를 보면 1건 더`;
}
function openSmp(title) {
  $("#smp-title").textContent = title || "본문 예시";
  $("#smp-note").textContent = SAMPLE_NOTE;
  $("#smp-back").classList.remove("hidden");
  $("#smp-sheet").classList.remove("hidden");
}
function closeSmp() {
  $("#smp-back").classList.add("hidden");
  $("#smp-sheet").classList.add("hidden");
}
$("#smp-close").onclick = closeSmp;
$("#smp-back").onclick = closeSmp;

/* 예시 만들기 — opts: {body, work_id, no, title} */
async function makeSample(opts) {
  const o = opts || {};
  SAMPLE_TEXT = "";
  const payload = Object.assign({}, o.body || {}, { work_id: o.work_id || 0, no: o.no || 0 });
  openSmp(o.title || (o.no ? `${o.no}화 본문 예시` : "본문 예시"));
  $("#smp-body").innerHTML = `<p class="smp-wait">설정을 반영해 쓰는 중…</p>`;
  $("#smp-foot").innerHTML = "";
  const r = await api("/api/writer/brief/sample", { method: "POST", body: JSON.stringify(payload) });
  if (r.sample) SAMPLE = r.sample;
  if (!r.ok) {
    $("#smp-body").innerHTML = `<p class="smp-wait">${escapeHtml(r.error || "예시를 만들지 못했어요.")}</p>`;
    smpFoot(o, r.need === "ad");
    return;
  }
  SAMPLE_TEXT = r.text || "";
  $("#smp-body").innerHTML = `<div class="smp-text">${escapeHtml(SAMPLE_TEXT).replace(/\n/g, "<br>")}</div>`;
  smpFoot(o, false);
}
function smpFoot(o, needAd) {
  const foot = $("#smp-foot");
  foot.innerHTML = `<span class="smp-left">${escapeHtml(smpLeftText())}</span>`;
  const mk = (label, fn, primary) => {
    const b = document.createElement("button");
    b.className = primary ? "primary" : "ghost small";
    b.textContent = label; b.onclick = fn; foot.appendChild(b); return b;
  };
  if (SAMPLE_TEXT) mk("예시 복사", async () => {
    try { await navigator.clipboard.writeText(SAMPLE_TEXT); notice("본문 예시를 복사했어요."); }
    catch (e) { notice("복사하지 못했어요. 글을 길게 눌러 복사해 주세요."); }
  }, true);
  if (SAMPLE.left > 0 && !needAd) mk("다시 써보기", () => makeSample(o));
  else mk("광고 보고 1건 더", () => watchAdForSample(o), true);
}
/* 광고를 끝까지 보면 예시 1건을 더 준다 */
function watchAdForSample(o) {
  const m = $("#ad-interstitial"), btn = $("#ad-close");
  m.classList.remove("hidden");
  let n = 5; btn.disabled = true; btn.textContent = `보는 중 (${n})`;
  const t = setInterval(() => {
    n -= 1;
    if (n <= 0) { clearInterval(t); btn.disabled = false; btn.textContent = "받기"; }
    else btn.textContent = `보는 중 (${n})`;
  }, 1000);
  btn.onclick = async () => {
    if (btn.disabled) return;
    clearInterval(t);
    m.classList.add("hidden");
    const r = await api("/api/writer/sample/ad", { method: "POST" });
    if (r && r.sample) SAMPLE = r.sample;
    smpFoot(o, SAMPLE.left <= 0);
    if (SAMPLE.left > 0) makeSample(o);
  };
  // 네이티브: AdMob.showRewardedAd() — 보상 콜백에서 위와 같이 처리한다
}

/* ── 플롯보기 시트 (페이지를 떠나지 않고 아래에서 올라온다) ── */
function openSheet(which) {
  $("#sh-title").textContent = `${CHAPTER.no}화`;
  document.querySelectorAll("#plot-sheet .st").forEach((b) =>
    b.classList.toggle("on", b.dataset.sht === which));
  $("#sheet-back").classList.remove("hidden");
  $("#plot-sheet").classList.remove("hidden");
  renderSheet(which);
}
function closeSheet() {
  $("#sheet-back").classList.add("hidden");
  $("#plot-sheet").classList.add("hidden");
}
function renderSheet(which) {
  const no = CHAPTER.no;
  const byNo = {}; (WORK.outline || []).forEach((o) => { byNo[o.no] = o; });
  const box = $("#sh-body");
  if (which === "near") {
    const chBy = {}; (WORK.chapters || []).forEach((c) => { chBy[c.no] = c; });
    const cell = (n, cls, label) => {
      const o = byNo[n], ch = chBy[n];
      if (!o && !ch && n !== no) return "";
      const t = (ch && ch.title) || (o && o.title) || "";
      const txt = (n < no && ch && ch.summary) ? ch.summary
        : (o && o.content) ? o.content : "아직 계획이 없어요.";
      return `<div class="near ${cls}"><div class="near-h">${label}</div>
        ${t ? `<b style="font-size:13px">${escapeHtml(t)}</b><br>` : ""}
        <p>${escapeHtml(txt)}</p></div>`;
    };
    box.innerHTML = cell(no - 1, "prev", `‹ ${no - 1}화 · 앞`)
      + cell(no, "now", `● ${no}화 · 지금 쓰는 중`)
      + cell(no + 1, "next", `${no + 1}화 › 다음`);
    return;
  }
  const o = byNo[no];
  box.innerHTML =
    `<p class="pl-syn${o && o.content ? "" : " empty"}">${o && o.content ? escapeHtml(o.content) : "아직 줄거리가 없어요."}</p>
     <div class="pl-acts"><button class="go">전체 회차 줄거리 보기</button></div>`;
  box.querySelector(".go").onclick = () => { closeSheet(); guard(() => showPlot(no)); };
}
$("#ed-plot").onclick = () => openSheet("current");
$("#sh-close").onclick = closeSheet;
$("#sheet-back").onclick = closeSheet;
document.querySelectorAll("#plot-sheet .st").forEach((b) => {
  b.onclick = () => openSheet(b.dataset.sht);
});

/* ── 메뉴 시트 (☰) ── */
function openMenu(where) {
  const box = $("#mn-body");
  box.innerHTML = "";
  const add = (label, fn, cls, icon) => {
    const b = document.createElement("button");
    b.innerHTML = (icon || "") + `<span>${escapeHtml(label)}</span>`;
    if (cls) b.className = cls;
    b.onclick = () => { closeMenu(); fn(); };
    box.appendChild(b);
  };
  if (where === "editor") {
    add("회차별 줄거리", () => guard(() => showPlot(CHAPTER.no)), "", ICO.book);
    add("본문 복사", async () => {
      await navigator.clipboard.writeText($("#ed-body").value);
      notice("본문을 복사했어요. 연재 플랫폼에 붙여넣으세요.");
    });
    add(".txt로 받기", () => {
      const blob = new Blob([`${$("#ed-title").value}\n\n${$("#ed-body").value}`],
        { type: "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${WORK.title}_${CHAPTER.no}화.txt`;
      a.click();
    });
    const lastNo = WORK.chapters.length ? WORK.chapters[WORK.chapters.length - 1].no : 0;
    if (CHAPTER && CHAPTER.no === lastNo) add("이 회차 삭제", deleteChapter, "danger", ICO.trash);
  } else if (where === "wizard") {
    add("내 작품 목록", () => { if (WZ) { WZ.live = false; wzSave(); WZ = null; } showHome(); }, "", ICO.home);
    add("설정", showSettings, "", ICO.gear);
  } else {
    if (WORK) add("작품 메인", () => openWork(WORK.id), "", ICO.pen);
    if (WORK) add("회차별 줄거리", () => showPlot(), "", ICO.book);
    add("내 작품 목록", showHome, "", ICO.home);
    add("설정", showSettings, "", ICO.gear);
  }
  $("#menu-back").classList.remove("hidden");
  $("#menu-sheet").classList.remove("hidden");
}
function closeMenu() {
  $("#menu-back").classList.add("hidden");
  $("#menu-sheet").classList.add("hidden");
}
$("#mn-close").onclick = closeMenu;
$("#menu-back").onclick = closeMenu;

async function deleteChapter() {
  if (!await askAction("이 회차를 삭제할까요?", "삭제", "취소")) return;
  const wid = WORK.id, cid = CHAPTER.id;
  const r = await api(`/api/writer/chapters/${cid}`, { method: "DELETE" });
  if (!r.ok) { notice(r.error); return; }
  try { localStorage.removeItem(draftKey(cid)); } catch (e) {}
  DIRTY = false;
  await openWork(wid);
}

/* ── 뒤로가기 — 브라우저/안드로이드 버튼으로 한 화면씩 되돌아간다 ── */
function goBack() {
  const open = ["w-editor", "w-plot", "w-wizard", "w-work", "w-plans", "w-pens", "w-settings"]
    .find((v) => !$(`#${v}`).classList.contains("hidden"));
  if (!$("#smp-sheet").classList.contains("hidden")) { closeSmp(); return; }
  if (!$("#menu-sheet").classList.contains("hidden")) { closeMenu(); return; }
  if (!$("#plot-sheet").classList.contains("hidden")) { closeSheet(); return; }
  if (open === "w-editor") { guard(() => openWork(WORK.id)); return; }
  if (open === "w-plot") { openWork(WORK.id); return; }
  if (open === "w-wizard") { wzBackStep(); return; }
  if (open === "w-plans") { leavePlans(); return; }
  if (open === "w-pens") { showBack(); return; }
  showHome();
}
window.addEventListener("popstate", () => { history.pushState(null, ""); goBack(); });

/* 시작 — 설정하다 만 게 있으면(새로고침·앱 재시작) 그 자리로 돌려놓는다 */
(async function boot() {
  await CONFIG_READY;
  await showHome();
  history.pushState(null, "");          // 뒤로가기를 잡아둘 한 칸
  await showHome();
})();

/* 브라우저가 이전 화면을 통째로 복원한 경우에도 작품 목록에서 시작한다.
   작성 중인 새 작품은 지우지 않고 '새 작품 만들기'에서 이어서 열 수 있다. */
window.addEventListener("pageshow", (event) => {
  if (event.persisted) showHome();
});
