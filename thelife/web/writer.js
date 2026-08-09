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

let WORK = null, CHAPTER = null;

/* 판매용 런치 버전 여부 — 서버 플래그.
   body.launch = 판매 빌드(자연어 설정 수정·회당글자수 등 제외 항목 숨김).
   body.nobody = 본문 쓰기 권한 없음(무료·라이트) → 본문 집필 UI 숨김.
   프로 구독자는 nobody가 풀려 본문 쓰기가 보이고, 펜으로 쓴다. */
let LAUNCH = true, TIER = "free", LIMITS = null, TIERS_INFO = null, EXPIRES = null;
let PENS = 0, PEN_NEEDED = false, PEN_PACKS = [];
(async () => {
  try {
    const cfg = await api("/api/writer/config");
    LAUNCH = !!(cfg && cfg.launch_mode);
    document.body.classList.toggle("launch", LAUNCH);
    document.body.classList.toggle("nobody", !(cfg && cfg.writing_enabled));
    if (cfg) {
      TIER = cfg.tier || "free"; LIMITS = cfg.limits; TIERS_INFO = cfg.tiers; EXPIRES = cfg.expires_at;
      PENS = cfg.pens || 0; PEN_NEEDED = !!cfg.pen_needed; PEN_PACKS = cfg.pen_packs || [];
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
    notice("펜이 부족해요. 펜을 충전하면 본문 1편(≤5,000자)을 쓸 수 있어요.");
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
  if (!confirm("정말 모든 작품과 데이터를 영구 삭제할까요?\n되돌릴 수 없습니다.")) return;
  if (!confirm("마지막 확인 — 정말 삭제합니다.")) return;
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
  bar.innerHTML = `
    <div class="plan-now">현재 플랜 <b>${L.label}</b>${expTxt}
      <span class="plan-lim">AI 회차 ${L.max_chapters}화 · 화당 ${L.syn_chars}자 · 인물 ${L.max_characters}명 · 작품 ${works}${L.style_learning ? " · 문체학습" : ""}</span></div>
    <button class="plan-upgrade" id="see-plans">구독 플랜 보기 · 변경</button>`;
  $("#see-plans").onclick = showPlans;
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
};
function _feat(icon, label, val, off) {
  return `<li class="${off ? "off" : ""}">${icon}<span>${label}</span><b>${val}</b></li>`;
}
function showPlans() { view("w-plans"); renderPlans(); }
function renderPlans() {
  const box = $("#plans-list");
  if (!box || !TIERS_INFO) return;
  box.innerHTML = PLAN_ORDER.map((t) => {
    const P = TIERS_INFO[t];
    const works = P.max_works >= 100000 ? "무제한" : P.max_works + "개";
    const cur = t === TIER;
    const feats = [
      _feat(IC.book, "AI 회차 줄거리", P.max_chapters + "화"),
      _feat(IC.pen, "화당 줄거리", P.syn_chars + "자"),
      _feat(IC.users, "AI 인물 생성", P.max_characters + "명"),
      _feat(IC.stack, "작품 수", works),
      _feat(IC.spark, "문체 학습", P.style_learning ? "✓" : "—", !P.style_learning),
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
$("#ad-upsell").onclick = () => { showHome(); notice("라이트·프로 요금제로 올리면 광고가 사라지고 더 많은 회차·인물을 생성할 수 있어요."); };

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
}

/* ---------- 펜 충전 화면 ---------- */
function showPens() { view("w-pens"); renderPens(); }
function showBack() { if (WORK) openWork(WORK.id); else showSettings(); }
function renderPenBar() {
  const bar = $("#pen-bar");
  if (!bar) return;
  bar.classList.toggle("hidden", !PEN_NEEDED);   // 개인 서버(펜 불필요)에선 숨김
  if (!PEN_NEEDED) return;
  bar.innerHTML = `<span class="pen-ic">🖊️</span> 남은 펜 <b>${PENS}</b>
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
/* 삭제 후 되돌리기 — onUndo를 실행하는 버튼이 함께 뜬다 */
function noticeUndo(t, onUndo) {
  $("#notice-text").textContent = t;
  const u = $("#notice-undo");
  u.classList.remove("hidden");
  u.onclick = async () => {
    u.classList.add("hidden");
    $("#notice").classList.add("hidden");
    await onUndo();
  };
  $("#notice").classList.remove("hidden");
}
$("#notice-close").onclick = () => $("#notice").classList.add("hidden");
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
  works.forEach((w) => {
    const el = document.createElement("button");
    el.className = "w-item";
    el.innerHTML = `<span class="del" data-id="${w.id}">✕</span><b>${w.title}</b>
      <small>${w.genre} · ${w.written}/${w.total_chapters}화</small>`;
    el.onclick = (ev) => {
      if (ev.target.classList.contains("del")) return delWork(w.id, w.title);
      openWork(w.id);
    };
    box.appendChild(el);
  });
}
async function delWork(id, title) {
  if (!confirm(`『${title}』을(를) 삭제할까요?`)) return;
  const r = await api(`/api/writer/works/${id}`, { method: "DELETE" });
  await showHome();
  if (r && r.undo) {
    noticeUndo(`『${title}』을(를) 삭제했어요.`, async () => {
      const rr = await api(`/api/writer/trash/${r.undo}/restore`, { method: "POST" });
      if (!rr.ok) { notice(rr.error || "되돌리기 실패"); return; }
      await showHome();
      notice("되돌렸어요.");
    });
  }
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
function removeRowUndo(el, boxId, reader, adder, label) {
  const box = $(boxId);
  const idx = [...box.children].indexOf(el);
  const data = reader(el);
  el.remove();
  noticeUndo(`${label}을(를) 삭제했어요.`, () => {
    adder(data);
    const added = box.lastElementChild;
    const ref = box.children[idx];
    if (ref && ref !== added) box.insertBefore(added, ref);
  });
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
  el.querySelector(".row-del").onclick = () => removeRowUndo(el, "#bd-chars", readChar, bdAddChar, "인물");
  $("#bd-chars").appendChild(el);
}

function bdAddCanon(d = {}) {
  const el = document.createElement("div");
  el.className = "bd-canon-row";
  el.innerHTML = `<button class="row-del" title="삭제">✕</button>
    <div class="row2"><input class="cn-name" placeholder="이름"><input class="cn-desc" placeholder="설명 (선택)"></div>`;
  el.querySelector(".cn-name").value = d.name || "";
  el.querySelector(".cn-desc").value = d.desc || "";
  el.querySelector(".row-del").onclick = () => removeRowUndo(el, "#bd-canon", readCanonRow, bdAddCanon, "고유명사");
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
  el.querySelector(".row-del").onclick = () => removeRowUndo(el, "#bd-outline", readOutlineRow, bdAddOutline, "회차");
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
    chars_per_chapter: Number($("#bd-cpc").value) || 5000,
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
$("#bd-ai-redraft").onclick = () => {
  if (!confirm("주인공·인물·세계관·문체 등 AI가 채운 부분을 비우고 처음부터 다시 생성할까요?\n(로그라인·결말·문체 표본은 그대로 둡니다)")) return;
  bdResetGenerated();
  bdDraft();
};

$("#bd-ai-outline").onclick = async () => {
  const b = bdCollect();
  if (!b.logline && !b.ending && !b.world_setting) {
    notice("회차 전개를 짜려면 로그라인·세계관·결말 중 하나는 채워주세요."); return;
  }
  if ($("#bd-outline").children.length &&
      !confirm("이미 짜둔 회차 전개를 지우고 새로 생성할까요?")) return;
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
  $("#wk-title").textContent = WORK.title;
  $("#wk-progress").textContent = `${d.chapters.length}/${WORK.total_chapters}화`;
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
  const written = WORK.chapters.length;
  if (!written) {
    box.innerHTML = `<p class="hint">아직 쓴 회차가 없어요. 전체 플롯은 위 '전체 플롯 보기'에서 보고 다듬을 수 있어요.<br>
      ${LAUNCH ? "" : "아래 '다음 회차 쓰기'로 1화를 시작하세요."}</p>`;
  }
  // 이미 쓴 회차만 목록에 보여준다 (예정 회차·비트 라벨은 표시하지 않음).
  WORK.chapters.forEach((ch) => {
    const el = document.createElement("button");
    el.className = "ch-item";
    el.innerHTML = `<span class="ch-no">${ch.no}화</span> ${escapeHtml(ch.title) || ""}`;
    el.onclick = () => openChapter(ch.id);
    box.appendChild(el);
  });
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
  $("#bible-cpc").value = String(WORK.chars_per_chapter || 5000);
  const bs = $("#brief-section");
  if (WORK.brief) {
    bs.classList.remove("hidden");
    $("#brief-edit").value = WORK.brief;
  } else {
    bs.classList.add("hidden");
  }
  const spb = $("#style-profile-box");
  if (WORK.style_profile) {
    spb.classList.remove("hidden");
    spb.textContent = WORK.style_profile;
  } else {
    spb.classList.add("hidden");
  }
  $("#bible-sample").value = WORK.style_sample || "";
  renderCanon();
  const box = $("#bible-chars");
  box.innerHTML = "";
  WORK.characters.forEach((c, idx) => {
    const el = document.createElement("div");
    el.className = "b-char";
    el.innerHTML = `
      <button class="edit-ch" title="편집">✎</button>
      <b>${c.name}</b><span class="arch">${c.archetype || ""}</span>
      <p>${c.role || ""}<br>욕망 — ${c.want || ""} · 결핍 — ${c.need || ""}<br>비밀 — ${c.secret || ""}</p>`;
    el.querySelector(".edit-ch").onclick = () => editChar(el, idx);
    box.appendChild(el);
  });
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
    box.innerHTML = `<p class="hint" style="opacity:.7">아직 고정된 이름이 없어요.</p>`;
    return;
  }
  box.innerHTML = "";
  keys.forEach((k) => {
    const row = document.createElement("div");
    row.className = "canon-row";
    row.innerHTML = `<b>${k}</b>${canon[k] ? ` — <span>${canon[k]}</span>` : ""}
      <button class="del" title="삭제">✕</button>`;
    row.querySelector(".del").onclick = async () => {
      const val = canon[k];
      await api(`/api/writer/works/${WORK.id}/canon/${encodeURIComponent(k)}`, { method: "DELETE" });
      delete WORK.canon[k];
      renderCanon();
      noticeUndo(`'${k}'을(를) 사전에서 지웠어요.`, async () => {
        const r = await api(`/api/writer/works/${WORK.id}/canon`, {
          method: "POST", body: JSON.stringify({ name: k, value: val }),
        });
        if (!r.ok) { notice(r.error || "되돌리기 실패"); return; }
        WORK.canon = r.canon;
        renderCanon();
      });
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
  const cpc = Number($("#bible-cpc").value) || WORK.chars_per_chapter || 5000;
  const r = await api(`/api/writer/works/${WORK.id}/bible`, {
    method: "PUT",
    body: JSON.stringify({
      title: $("#bible-title").value.trim(),
      ending: $("#bible-ending").value.trim(),
      characters: WORK.characters, relations: WORK.relations, beats: WORK.beats,
      total_chapters: total, chars_per_chapter: cpc,
    }),
  });
  if (!r.ok) { notice(r.error || "저장 실패"); return; }
  WORK.title = $("#bible-title").value.trim(); $("#wk-title").textContent = WORK.title;
  WORK.ending = $("#bible-ending").value.trim();
  WORK.total_chapters = total; WORK.chars_per_chapter = cpc;
  $("#wk-progress").textContent = `${WORK.chapters.length}/${total}화`;
}
$("#bible-save-core").onclick = async () => {
  await saveBible();
  renderChapters();  // 총 회차 바뀌면 예정 회차 목록도 갱신
  notice("저장했어요. 이후 회차부터 반영됩니다.");
};

$("#brief-save").onclick = async () => {
  const brief = $("#brief-edit").value;
  const r = await api(`/api/writer/works/${WORK.id}/brief`, {
    method: "PUT", body: JSON.stringify({ brief }),
  });
  if (!r.ok) { notice(r.error || "저장 실패"); return; }
  WORK.brief = brief;
  notice("설명서를 저장했어요. 이후 모든 회차가 이 내용을 절대 기준으로 씁니다.");
};

$("#bible-learn").onclick = async () => {
  const sample = $("#bible-sample").value.trim();
  if (sample.length < 300) { notice("문체를 배우려면 표본이 300자는 넘어야 해요."); return; }
  busy("문체를 학습하는 중… (15초쯤)");
  const r = await api(`/api/writer/works/${WORK.id}/style`, {
    method: "POST", body: JSON.stringify({ sample }),
  });
  unbusy();
  if (!r.ok) { notice(r.error + (r.detail ? `\n\n[원인] ${r.detail}` : "")); return; }
  WORK.style_profile = r.profile;
  WORK.style_sample = sample;
  renderBible();
  notice("문체를 배웠어요. 다음 회차부터 이 결로 씁니다.\n학습된 프로파일은 문체 섹션에서 확인하세요.");
};

$("#bible-revise").onclick = async () => {
  const directive = $("#bible-cmd").value.trim();
  if (!directive) { notice("무엇을 고칠지 알려주세요."); return; }
  busy("설정집을 고치는 중…");
  const r = await api(`/api/writer/works/${WORK.id}/bible/revise`, {
    method: "POST", body: JSON.stringify({ directive }),
  });
  unbusy();
  if (!r.ok) { notice((r.error || "실패") + (r.detail ? `\n\n[원인] ${r.detail}` : "")); return; }
  $("#bible-cmd").value = "";
  const d = await api(`/api/writer/works/${WORK.id}`);
  WORK = d.work; WORK.chapters = d.chapters;
  renderBible();
  notice("설정집을 고쳤어요. 이후 회차부터 반영됩니다.\n(이미 쓴 회차는 편집기에서 직접 고치거나 '다시 쓰기' 하세요)");
};

/* ---------- 전체 플롯 보기 → 플롯/가이드 페이지로 ---------- */
$("#btn-plot").onclick = () => showPlot();

/* ---------- 모든 회차 다시 쓰기 (앞→뒤 순차, 설정·이름·결말 고정) ---------- */
$("#btn-rewrite-all").onclick = async () => {
  const chs = WORK.chapters;
  if (!chs.length) { notice("아직 쓴 회차가 없어요."); return; }
  const penNote = PEN_NEEDED ? `\n회차마다 펜 1개가 들어요 (총 ${chs.length}개 필요, 보유 ${PENS}개).` : "";
  if (!confirm(`이미 쓴 ${chs.length}개 회차를 1화부터 순서대로 모두 다시 씁니다.\n` +
    `제목·인물 이름·결말·설명서 등 기본 설정은 절대 바뀌지 않아요.\n` +
    `시간이 오래 걸리고 AI 사용량이 많이 듭니다.${penNote}\n진행할까요?`)) return;
  for (let i = 0; i < chs.length; i++) {
    busy(`모든 회차 다시 쓰는 중… (${i + 1}/${chs.length}화)`);
    const r = await api(`/api/writer/chapters/${chs[i].id}/regenerate`, {
      method: "POST", body: JSON.stringify({ directive: "", forward: true }),
    });
    if (!r.ok) {
      unbusy();
      if (handleBodyNeed(r)) { await openWork(WORK.id); return; }
      notice(`${chs[i].no}화에서 멈췄어요.\n\n${r.error || ""}${r.detail ? "\n" + r.detail : ""}`);
      await openWork(WORK.id);
      return;
    }
    setPens(r.pens);
  }
  unbusy();
  await openWork(WORK.id);
  notice("모든 회차를 다시 썼어요.");
};

/* ---------- 회차 쓰기 ---------- */
$("#btn-write").onclick = async () => {
  const cpc = (WORK.chars_per_chapter || 5000).toLocaleString();
  busy(`${WORK.chapters.length + 1}화를 쓰는 중… (${cpc}자, 30초~1분)`);
  const r = await api(`/api/writer/works/${WORK.id}/chapters`, {
    method: "POST", body: JSON.stringify({ directive: $("#directive").value.trim() }),
  });
  unbusy();
  if (!r.ok) {
    if (handleBodyNeed(r)) return;             // 프로/펜 필요 → 안내·이동
    notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : "") +
      (r.trace ? `\n${r.trace.join("\n")}` : ""));
    return;
  }
  setPens(r.pens);
  $("#directive").value = "";
  await openWork(WORK.id);
  openChapter(r.id);
};

/* ══════════ 새 작품 — 단계별 설계 (위저드) ══════════
   아이디어 한 줄만 받고, 세계관·인물·플롯은 AI가 만든다.
   사용자는 확인하고 마음에 안 드는 부분만 다시 만든다. */
const WZ_TOTALS = [15, 25, 40, 70];
const WZ_OTHER = "기타 (직접 입력)";
let WZ = null;

function startWizard() {
  WZ = { i: 0, phase: "form", total: 25, sel: {}, other: {}, detail: {},
         basic: {}, cast: [], castOpen: -1, draft: null, outline: [], paints: {} };
  view("w-wizard");
  wzRender();
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
  $("#wz-sub").textContent = s.sub ||
    (s.kind ? "" : (s.pick === 0 ? "여러 개 고를 수 있어요."
      : s.pick > 1 ? `최대 ${s.pick}개까지 고를 수 있어요.` : "하나만 고르세요."));
  // 진행 표시 (전체 단계 대비)
  const prog = Math.round(((WZ.i + 1) / wzStepCount()) * 4);
  document.querySelectorAll("#w-wizard .wz-dot").forEach((d) =>
    d.classList.toggle("on", +d.dataset.s <= Math.max(1, prog)));
  $("#wz-count").textContent = `${WZ.i + 1}/${wzStepCount()}`;
  $("#wz-back").style.visibility = "";
  const box = $("#wz-step-body");
  box.innerHTML = "";
  WZ.paints = {};                     // 지운 화면의 옛 갱신함수는 버린다
  if (s.kind === "text") wzRenderText(box, s);
  else if (s.kind === "cast") wzRenderCast(box, s);
  else wzRenderPick(box, s, WZ.sel, WZ.other, WZ.detail, s.id);
  wzFoot(s);
  window.scrollTo(0, 0);
}
function wzFoot(s) {
  const foot = $("#wz-foot");
  foot.innerHTML = "";
  const mk = (label, fn, ghost) => {
    const b = document.createElement("button");
    b.className = ghost ? "btn-ghost2" : "btn-main";
    b.textContent = label; b.onclick = fn; foot.appendChild(b); return b;
  };
  const last = WZ.i >= wzStepCount() - 1;
  mk(last ? "이대로 만들기 ✨" : "다음 →", () => {
    if (last) wzGenerate(); else { WZ.i++; wzRender(); }
  });
  if (s.opts) mk("✨ AI에게 추천받기", () => wzSuggest(s), true);
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
    el.oninput = () => { WZ.basic[f.k] = el.value; };
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
    b.onclick = () => { WZ.total = n; tb.forEach((x) => x.el.classList.toggle("on", x.n === n)); };
    tb.push({ el: b, n });
    tc.appendChild(b);
  });
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
    el.oninput = () => { detail[key] = el.value; };
    box.appendChild(detailBox);
  }
  paint();
  WZ.paints[key] = paint;             // AI 추천 뒤 '표시만' 갱신할 때 쓴다
  return paint;
}
function wzToggle(sel, key, val, pick) {
  const arr = sel[key] || (sel[key] = []);
  const at = arr.indexOf(val);
  if (at >= 0) { arr.splice(at, 1); return; }
  if (pick === 1) { arr.length = 0; arr.push(val); return; }   // 하나만 (배열은 그대로 두고 내용만 바꾼다)
  if (pick > 1 && arr.length >= pick) arr.shift();   // 최대 개수 넘으면 오래된 것 밀어내기
  arr.push(val);
}
/* ── AI에게 추천받기 ── */
async function wzSuggest(s, target) {
  const opts = (s.opts || []).map((o) => (typeof o === "string" ? o : o.v));
  busy("AI가 고르는 중…");
  const r = await api("/api/writer/brief/suggest", {
    method: "POST",
    body: JSON.stringify({ question: s.title, options: opts,
      pick: s.pick === 0 ? 3 : (s.pick || 1), context: wzContext() }),
  });
  unbusy();
  if (!r.ok) { notice(r.error || "추천을 받지 못했어요."); return; }
  (target || WZ.sel)[s.id] = r.picked;
  // 표시만 그 자리에서 갱신 (화면을 다시 그리지 않아 보던 위치가 유지된다)
  if (WZ.paints[s.id]) WZ.paints[s.id]();
  else if (target) wzRenderCastDetail(); else wzRender();
  if (r.reason) notice(`AI 추천: ${r.picked.join(", ")}\n\n${r.reason}`);
}

/* ── 인물 설정 ── */
function wzRenderCast(box, s) {
  if (WZ.castOpen >= 0) { wzRenderCastDetail(box); return; }
  const list = document.createElement("div");
  list.className = "cast-list";
  WZ.cast.forEach((c, i) => {
    const el = document.createElement("div");
    el.className = "cast-row";
    el.innerHTML = `<div class="cast-main">
        <input class="cast-n" placeholder="이름" value="${escapeHtml(c.name || "")}">
        <input class="cast-a" placeholder="나이" value="${escapeHtml(c.age || "")}">
      </div>
      <button class="cast-more">자세히 ›</button>
      <button class="cast-del" title="삭제">✕</button>`;
    el.querySelector(".cast-n").oninput = (e) => { c.name = e.target.value; };
    el.querySelector(".cast-a").oninput = (e) => { c.age = e.target.value; };
    el.querySelector(".cast-more").onclick = () => { WZ.castOpen = i; wzRender(); };
    el.querySelector(".cast-del").onclick = () => {
      removeRowUndo(el, ".cast-list", () => c, () => {}, "인물");
      WZ.cast.splice(i, 1); wzRender();
    };
    list.appendChild(el);
  });
  box.appendChild(list);
  const add = document.createElement("button");
  add.className = "btn-ghost2";
  add.textContent = "＋ 인물 추가";
  add.onclick = () => { WZ.cast.push({ name: "", age: "", sel: {}, other: {}, detail: {} }); wzRender(); };
  box.appendChild(add);
}
function wzRenderCastDetail(box) {
  box = box || $("#wz-step-body");
  box.innerHTML = "";
  WZ.paints = {};
  const c = WZ.cast[WZ.castOpen];
  if (!c) { WZ.castOpen = -1; wzRender(); return; }
  $("#wz-kicker").textContent = "인물 · 자세히";
  $("#wz-title").textContent = c.name || "이 인물";
  $("#wz-sub").textContent = "비워두면 AI가 알아서 채워요.";
  WZ_CAST_SPEC.forEach((cs) => {
    const h = document.createElement("div");
    h.innerHTML = `<div class="wz-label">${cs.n}. ${cs.title}
      <button class="mini-ai" data-id="${cs.id}">✨ 추천</button></div>`;
    h.querySelector(".mini-ai").onclick = () => wzSuggest(cs, c.sel);
    box.appendChild(h);
    wzRenderPick(box, cs, c.sel, c.other, c.detail, cs.id);
  });
  const foot = $("#wz-foot");
  foot.innerHTML = "";
  const done = document.createElement("button");
  done.className = "btn-main";
  done.textContent = "이 인물 완료 ✓";
  done.onclick = () => { WZ.castOpen = -1; wzRender(); };
  foot.appendChild(done);
  window.scrollTo(0, 0);
}
/* 선택 단계가 끝난 뒤의 화면 (생성 중 / 확인 / 회차) */
function wzGo(phase) {
  WZ.phase = phase;
  const pane = { gen: "wzp-2", result: "wzp-3", outline: "wzp-4" }[phase];
  ["wzp-1", "wzp-2", "wzp-3", "wzp-4"].forEach((v) =>
    $(`#${v}`).classList.toggle("hidden", v !== pane));
  document.querySelectorAll("#w-wizard .wz-dot").forEach((d) => d.classList.add("on"));
  $("#wz-count").textContent = { gen: "생성 중", result: "확인", outline: "완성" }[phase] || "";
  $("#wz-back").style.visibility = (phase === "gen") ? "hidden" : "";
  const foot = $("#wz-foot");
  foot.innerHTML = "";
  const btn = (label, fn, ghost) => {
    const b = document.createElement("button");
    b.className = ghost ? "btn-ghost2" : "btn-main";
    b.textContent = label; b.onclick = fn; foot.appendChild(b); return b;
  };
  if (phase === "result") {
    btn("좋아요, 다음 →", wzOutline);
    btn("🔄 인물 전체 다시 만들기", () => wzRedraw("characters"), true);
  }
  if (phase === "outline") btn("완성! 작품 시작하기 🎉", wzFinish);
  window.scrollTo(0, 0);
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
      secret: pick("secret"), facade: pick("facade"), truth: pick("truth"), need: "", relation: "" });
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
    world_setting: world || d.world_setting || "",
    world_rules: d.world_rules || "", taboos: d.taboos || "",
    style: style || d.style || "",
    structure: structure,
    protagonist: (d.protagonist && d.protagonist.name) ? d.protagonist
      : (lead ? { name: lead.name, age: lead.age, personality: lead.personality,
                  want: lead.want, need: lead.fear, secret: lead.secret } : {}),
    characters: (d.characters && d.characters.length) ? d.characters : cast,
    canon: d.canon || [],
    outline: WZ.outline || [],
  }, extra || {});
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
  $("#wz-gen-h").textContent = "이야기를 짜고 있어요";
  wzTasks([["세계관 만드는 중", "now"], ["인물 만드는 중", ""], ["플롯 정리", ""]]);
  const r = await api("/api/writer/brief/draft", {
    method: "POST", body: JSON.stringify(wzBody()),
  });
  if (!r.ok) {
    notice((r.error || "만들지 못했어요.") + (r.detail ? `\n\n${r.detail}` : ""));
    WZ.phase = "form"; wzRender();
    return;
  }
  WZ.draft = r.draft || {};
  wzTasks([["세계관 만드는 중", "done"], ["인물 만드는 중", "done"], ["플롯 정리", "done"]]);
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
  renderWzResult();
}
function renderWzResult() {
  const d = WZ.draft || {};
  const box = $("#wz-result");
  const world = [d.world_setting, d.world_rules, d.taboos].filter(Boolean).join("\n\n");
  let h = `<div class="wzc"><h3>📖 ${escapeHtml(d.title || "제목 미정")}<span class="tag">AI 생성</span></h3>
      <p>${escapeHtml(d.logline || "")}</p></div>
    <div class="wzc"><h3>🌍 세계관</h3><p>${escapeHtml(world || "—")}</p>
      <div class="wzc-acts"><button data-rd="world">🔄 세계관 다시</button></div></div>`;
  const cast = [];
  if (d.protagonist && d.protagonist.name) cast.push(Object.assign({ role: "주인공" }, d.protagonist));
  (d.characters || []).forEach((c) => cast.push(c));
  cast.forEach((c, i) => {
    const col = i === 0 ? "linear-gradient(135deg,#8b70ff,#6a54f0)"
      : ["linear-gradient(135deg,#d9559b,#c23f86)", "linear-gradient(135deg,#d64b43,#b03b34)",
         "linear-gradient(135deg,#3f8ae0,#2f7fce)", "linear-gradient(135deg,#2fa07f,#258066)"][i % 4];
    h += `<div class="wzp"><div class="wzp-av" style="background:${col}">${escapeHtml((c.name || "?").slice(0, 1))}</div>
      <div><b>${escapeHtml(c.name || "")}</b><span class="role">${escapeHtml(c.role || "")}</span>
      <p>${escapeHtml([c.relation, c.want && "욕망 " + c.want, c.need && "결핍 " + c.need,
        c.secret && "비밀 " + c.secret].filter(Boolean).join(" · "))}</p></div></div>`;
  });
  if (d.ending) h += `<div class="wzc"><h3>🎯 결말</h3><p>${escapeHtml(d.ending)}</p></div>`;
  box.innerHTML = h;
  box.querySelectorAll("[data-rd]").forEach((b) => { b.onclick = () => wzRedraw(b.dataset.rd); });
}
async function wzOutline() {
  wzGo("gen");
  $("#wz-gen-h").textContent = "회차별 전개를 짜고 있어요";
  wzTasks([["설정 정리", "done"], [`1화~${WZ.total}화 흐름 만드는 중`, "now"]]);
  const r = await api("/api/writer/brief/outline", { method: "POST", body: JSON.stringify(wzBody()) });
  if (!r.ok) {
    notice((r.error || "전개를 못 만들었어요.") + (r.detail ? `\n\n${r.detail}` : ""));
    wzGo("result"); return;
  }
  WZ.outline = r.outline || [];
  renderWzOutline();
  wzGo("outline");
}
function renderWzOutline() {
  const d = WZ.draft || {};
  const rows = (WZ.outline || []).map((o) =>
    `<div class="wz-ep"><span class="n">${o.no}화</span><div><b>${escapeHtml(o.title || "")}</b>
      <span>${escapeHtml((o.content || "").slice(0, 90))}</span></div></div>`).join("");
  $("#wz-outline").innerHTML =
    `<div class="wzc"><h3>🗺 총 ${WZ.outline.length || WZ.total}화 · 결말 고정</h3>
       <p style="color:var(--text)">${escapeHtml(d.ending || "")}</p></div>
     <div class="wzc" style="padding:6px 16px">${rows || "<p>전개가 비어 있어요.</p>"}</div>`;
}
async function wzFinish() {
  busy("작품을 만드는 중…");
  const r = await api("/api/writer/works/build", { method: "POST", body: JSON.stringify(wzBody()) });
  unbusy();
  if (!r.ok) { notice((r.error || "작품을 만들지 못했어요.") + (r.detail ? `\n\n${r.detail}` : "")); return; }
  WZ = null;
  await openWork(r.id);
  notice("작품이 만들어졌어요! 회차를 눌러 집필을 시작하세요.");
}
$("#wz-back").onclick = () => {
  if (!WZ) { showHome(); return; }
  if (WZ.phase === "outline") { wzGo("result"); return; }
  if (WZ.phase === "result") { WZ.phase = "form"; wzRender(); return; }
  if (WZ.castOpen >= 0) { WZ.castOpen = -1; wzRender(); return; }   // 인물 상세 → 목록
  if (WZ.i > 0) { WZ.i--; wzRender(); return; }                     // 앞 단계로
  showHome();
};

/* ══════════ 전체 플롯 / 가이드 (아코디언) ══════════
   제목을 누르면 그 화의 줄거리와 집필 가이드가 펼쳐지고, 다른 제목을 누르면 접힌다. */
let PLOT_OPEN = 0;                     // 지금 펼쳐진 화 번호 (0=없음)
const GUIDE_CACHE = {};                // {no: guide}

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
  $("#pl-meta").textContent =
    `총 ${rows.length}화 · ${WORK.chapters.length}화 집필됨 — 제목을 누르면 줄거리와 가이드가 열려요`;
  const box = $("#pl-list");
  box.innerHTML = "";
  rows.forEach(({ no, o, ch }) => {
    const open = PLOT_OPEN === no;
    const title = (ch && ch.title) || (o && o.title) || `${no}화`;
    const el = document.createElement("div");
    el.className = "pl-item" + (open ? " open" : "");
    el.innerHTML =
      `<button class="pl-head"><span class="pl-no">${no}화</span>
         <span class="pl-t">${escapeHtml(title)}</span>
         <span class="pl-chev">${open ? "▲" : "▼"}</span></button>`;
    el.querySelector(".pl-head").onclick = () => {
      PLOT_OPEN = open ? 0 : no;       // 같은 걸 누르면 접기, 다른 걸 누르면 그것만 열기
      renderPlotList();
      if (!open) loadGuide(no);
    };
    if (open) {
      const pane = document.createElement("div");
      pane.className = "pl-pane";
      const syn = (o && o.content) ? escapeHtml(o.content)
        : (ch && ch.summary ? escapeHtml(ch.summary) : "");
      pane.innerHTML =
        `<p class="pl-syn${syn ? "" : " empty"}">${syn || "아직 줄거리가 없어요."}</p>
         <span class="pl-gtag">가이드</span>
         <div class="g-wrap" id="g-${no}">${guideHtml(GUIDE_CACHE[no])}</div>
         <div class="pl-acts">
           <button class="regen">🔄 가이드 새로</button>
           ${ch ? `<button class="go">✍ 이 화 쓰기</button>`
                : `<button class="go">✍ 이 화 쓰기</button>`}
         </div>`;
      pane.querySelector(".regen").onclick = () => loadGuide(no, true);
      pane.querySelector(".go").onclick = () => openChapterByNo(no);
      el.appendChild(pane);
    }
    box.appendChild(el);
  });
}
const GUIDE_ORDER = ["목표", "연결", "갈등", "인물", "사건", "맺음"];
function guideHtml(g) {
  if (!g) return `<p class="g-v" style="padding:8px 0">가이드를 불러오는 중…</p>`;
  let h = GUIDE_ORDER.map((k) => g[k]
    ? `<div class="g-row"><span class="g-k">${k}</span><span class="g-v">${escapeHtml(g[k])}</span></div>`
    : "").join("");
  if (g["반복주의"]) {
    h += `<div class="g-row warn"><span class="g-k">반복 주의</span>
            <span class="g-v">${escapeHtml(g["반복주의"])}</span></div>`;
  }
  return h || `<p class="g-v" style="padding:8px 0">가이드가 없어요.</p>`;
}
async function loadGuide(no, force) {
  const slot = $(`#g-${no}`);
  if (slot && (force || !GUIDE_CACHE[no])) {
    slot.innerHTML = `<p class="g-v" style="padding:8px 0">가이드를 ${force ? "새로 만드는" : "불러오는"} 중…</p>`;
  }
  const r = await api(`/api/writer/works/${WORK.id}/guide`, {
    method: "POST", body: JSON.stringify({ no, force: !!force }),
  });
  if (!r.ok) {
    const s = $(`#g-${no}`);
    if (s) s.innerHTML = `<p class="g-v" style="padding:8px 0">${escapeHtml(r.error || "가이드를 못 만들었어요.")}</p>`;
    return;
  }
  GUIDE_CACHE[no] = r.guide;
  const s2 = $(`#g-${no}`);
  if (s2) s2.innerHTML = guideHtml(r.guide);
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
/* 번호로 열기 — 아직 안 쓴 화면 새로 만들지 않고 안내한다 */
function openChapterByNo(no) {
  const ch = (WORK.chapters || []).find((c) => c.no === no);
  if (ch) { openChapter(ch.id); return; }
  notice(`${no}화는 아직 만들어지지 않았어요.\n회차 목록에서 먼저 만들어 주세요.`);
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
  if (!quiet) notice("저장했어요.");
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
  const list = (WORK.chapters || []).slice().sort((a, b) => a.no - b.no);
  const i = list.findIndex((c) => c.id === CHAPTER.id);
  const t = list[i + delta];
  if (!t) { notice(delta > 0 ? "마지막 회차예요." : "첫 회차예요."); return; }
  guard(() => openChapter(t.id));
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
     <span class="pl-gtag">가이드</span>
     <div class="g-wrap" id="g-${no}">${guideHtml(GUIDE_CACHE[no])}</div>
     <div class="pl-acts"><button class="regen">🔄 가이드 새로</button>
       <button class="go">📖 전체 플롯 열기</button></div>`;
  box.querySelector(".regen").onclick = () => loadGuide(no, true);
  box.querySelector(".go").onclick = () => { closeSheet(); guard(() => showPlot(no)); };
  if (!GUIDE_CACHE[no]) loadGuide(no);
}
$("#ed-plot").onclick = () => openSheet("guide");
$("#sh-close").onclick = closeSheet;
$("#sheet-back").onclick = closeSheet;
document.querySelectorAll("#plot-sheet .st").forEach((b) => {
  b.onclick = () => openSheet(b.dataset.sht);
});

/* ── 메뉴 시트 (☰) ── */
function openMenu(where) {
  const box = $("#mn-body");
  box.innerHTML = "";
  const add = (label, fn, cls) => {
    const b = document.createElement("button");
    b.textContent = label;
    if (cls) b.className = cls;
    b.onclick = () => { closeMenu(); fn(); };
    box.appendChild(b);
  };
  if (where === "editor") {
    add("📖 전체 플롯 / 가이드", () => guard(() => showPlot(CHAPTER.no)));
    add("📋 본문 복사", async () => {
      await navigator.clipboard.writeText($("#ed-body").value);
      notice("본문을 복사했어요. 연재 플랫폼에 붙여넣으세요.");
    });
    add("⬇ .txt로 받기", () => {
      const blob = new Blob([`${$("#ed-title").value}\n\n${$("#ed-body").value}`],
        { type: "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${WORK.title}_${CHAPTER.no}화.txt`;
      a.click();
    });
    const lastNo = WORK.chapters.length ? WORK.chapters[WORK.chapters.length - 1].no : 0;
    if (CHAPTER && CHAPTER.no === lastNo) add("🗑 이 회차 삭제", deleteChapter, "danger");
  } else {
    add("✍ 작품 화면", () => openWork(WORK.id));
    add("⚙ 설정", showSettings);
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
  if (!confirm("이 회차를 삭제할까요?")) return;
  const wid = WORK.id, cid = CHAPTER.id;
  const r = await api(`/api/writer/chapters/${cid}`, { method: "DELETE" });
  if (!r.ok) { notice(r.error); return; }
  try { localStorage.removeItem(draftKey(cid)); } catch (e) {}
  DIRTY = false;
  await openWork(wid);
  if (r.undo) {
    noticeUndo("회차를 삭제했어요.", async () => {
      const rr = await api(`/api/writer/trash/${r.undo}/restore`, { method: "POST" });
      if (!rr.ok) { notice(rr.error || "되돌리기 실패"); return; }
      await openWork(wid);
      notice("되돌렸어요.");
    });
  }
}

showHome();
