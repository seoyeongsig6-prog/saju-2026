/* The Novelist — 프런트엔드 */
const $ = (s) => document.querySelector(s);

let UID = localStorage.getItem("thelife_uid");
if (!UID) {
  UID = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now());
  localStorage.setItem("thelife_uid", UID);
}
const api = async (path, opts = {}) => {
  const r = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-User-Id": UID, ...(opts.headers || {}) },
  });
  return r.json();
};

let WORK = null, CHAPTER = null;

/* ---------- 테마 (밝게/어둡게 — 기본 밝게) ---------- */
function applyTheme(t) {
  document.body.dataset.theme = t;
  localStorage.setItem("thelife_theme", t);
  const b = $("#theme-toggle");
  if (b) b.textContent = t === "dark" ? "☀️" : "🌙";
}
applyTheme(localStorage.getItem("thelife_theme") || "light");
$("#theme-toggle").onclick = () =>
  applyTheme(document.body.dataset.theme === "dark" ? "light" : "dark");

function view(id) {
  ["w-home", "w-build", "w-work", "w-editor"].forEach((v) =>
    $(`#${v}`).classList.toggle("hidden", v !== id));
}
function notice(t) { $("#notice-text").textContent = t; $("#notice").classList.remove("hidden"); }
$("#notice-close").onclick = () => $("#notice").classList.add("hidden");
function busy(t) { $("#busy-text").textContent = t; $("#busy").classList.remove("hidden"); }
function unbusy() { $("#busy").classList.add("hidden"); }

/* ---------- 작품 목록 ---------- */
async function showHome() {
  view("w-home");
  const d = await api("/api/writer/works");
  const box = $("#w-list");
  box.innerHTML = "";
  (d.works || []).forEach((w) => {
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
  if (!confirm(`『${title}』을(를) 삭제할까요? 되돌릴 수 없어요.`)) return;
  await api(`/api/writer/works/${id}`, { method: "DELETE" });
  showHome();
}
/* ---------- 새 작품 = 작품설명서 빌더로 바로 ---------- */
const bdVal = (id) => $("#" + id).value.trim();

$("#w-new").onclick = () => {
  view("w-build");
  if (!$("#bd-chars").children.length) { bdAddChar(); bdAddChar(); }
  if (!$("#bd-canon").children.length) { bdAddCanon(); }
};

function bdAddChar(d = {}) {
  const el = document.createElement("div");
  el.className = "bd-char-row";
  el.innerHTML = `
    <button class="row-del" title="삭제">✕</button>
    <div class="row2">
      <input class="c-name" placeholder="이름">
      <input class="c-role" placeholder="역할 (적대자·조력자·애정상대…)">
    </div>
    <input class="c-rel" placeholder="주인공과의 관계">
    <div class="row2">
      <input class="c-want" placeholder="욕망(want)">
      <input class="c-need" placeholder="결핍(need)">
    </div>
    <input class="c-secret" placeholder="비밀 (선택)">`;
  const set = (cls, v) => { el.querySelector(cls).value = v || ""; };
  set(".c-name", d.name); set(".c-role", d.role); set(".c-rel", d.relation);
  set(".c-want", d.want); set(".c-need", d.need); set(".c-secret", d.secret);
  el.querySelector(".row-del").onclick = () => el.remove();
  $("#bd-chars").appendChild(el);
}

function bdAddCanon(d = {}) {
  const el = document.createElement("div");
  el.className = "bd-canon-row";
  el.innerHTML = `<button class="row-del" title="삭제">✕</button>
    <div class="row2"><input class="cn-name" placeholder="이름"><input class="cn-desc" placeholder="설명 (선택)"></div>`;
  el.querySelector(".cn-name").value = d.name || "";
  el.querySelector(".cn-desc").value = d.desc || "";
  el.querySelector(".row-del").onclick = () => el.remove();
  $("#bd-canon").appendChild(el);
}

function bdAddOutline(d = {}) {
  const el = document.createElement("div");
  el.className = "bd-outline-row";
  el.innerHTML = `<button class="row-del" title="삭제">✕</button>
    <div class="o-head"><input class="o-no" type="number" min="1" placeholder="화"><input class="o-title" placeholder="제목"></div>
    <textarea class="o-content" rows="2" placeholder="이 화의 핵심 사건 — 누가 무엇을 하고 무엇이 바뀌는지"></textarea>`;
  el.querySelector(".o-no").value = d.no || "";
  el.querySelector(".o-title").value = d.title || "";
  el.querySelector(".o-content").value = d.content || "";
  el.querySelector(".row-del").onclick = () => el.remove();
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
    title: bdVal("bd-title"), genre: bdVal("bd-genre"),
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
      name: r.querySelector(".c-name").value.trim(), role: r.querySelector(".c-role").value.trim(),
      relation: r.querySelector(".c-rel").value.trim(), want: r.querySelector(".c-want").value.trim(),
      need: r.querySelector(".c-need").value.trim(), secret: r.querySelector(".c-secret").value.trim(),
    })).filter((c) => c.name),
    canon: [...$("#bd-canon").querySelectorAll(".bd-canon-row")].map((r) => ({
      name: r.querySelector(".cn-name").value.trim(), desc: r.querySelector(".cn-desc").value.trim(),
    })).filter((c) => c.name),
    style: bdVal("bd-style"), style_sample: bdVal("bd-sample"), ending: bdVal("bd-ending"),
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
   ["bd-ending", d.ending], ["bd-style", d.style]].forEach(([id, v]) => bdSetIfEmpty(id, v));
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
  ["bd-intent", "bd-world", "bd-rules", "bd-taboos", "bd-p-name", "bd-p-age", "bd-p-job",
   "bd-p-personality", "bd-p-want", "bd-p-need", "bd-p-secret", "bd-p-arc", "bd-style"]
    .forEach((id) => { $("#" + id).value = ""; });
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
  notice(`${(r.outline || []).length}개 회차 전개를 채웠어요. 각 칸을 자유롭게 고치세요.`);
};

$("#bd-go").onclick = async () => {
  const b = bdCollect();
  if (!b.logline && !b.ending) { notice("최소한 로그라인이나 결말 중 하나는 채워주세요."); return; }
  busy("설명서를 정리하고 설계도(인물·관계·15비트)를 만드는 중… (30초쯤)");
  const r = await api("/api/writer/works/build", { method: "POST", body: JSON.stringify(b) });
  unbusy();
  if (!r.ok) {
    notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : "")); return;
  }
  if (r.outline_chapters >= 3) {
    notice(`${r.outline_chapters}개 회차의 지정 내용이 저장됐어요.\n각 회차는 이 전개 그대로 집필됩니다.`);
  }
  openWork(r.id);
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
    box.innerHTML = `<p class="hint">아직 첫 회차가 없어요. 아래 '다음 회차 쓰기'로 1화를 시작하세요.<br>
      아래 '예정 회차'의 계획을 눌러 미리 각 화 줄거리를 짜둘 수 있어요.</p>`;
  }
  WORK.chapters.forEach((ch) => {
    const el = document.createElement("button");
    el.className = "ch-item";
    const o = (WORK.outline || []).find((x) => x.no === ch.no);
    const beat = WORK.beats[ch.beat_idx] || {};
    el.innerHTML = `<span class="ch-no">${ch.no}화</span> ${escapeHtml(ch.title) || ""}
      <small>${o ? "📋 계획" : (beat.name || "")}</small>`;
    el.onclick = () => openChapter(ch.id);
    box.appendChild(el);
  });

  // 예정 회차 — 아직 안 쓴 회차를 계획대로 보여주고 매화 편집
  const total = WORK.total_chapters || 0;
  const byNo = {};
  (WORK.outline || []).forEach((o) => { byNo[o.no] = o; });
  const nos = [];
  for (let n = written + 1; n <= total; n++) nos.push(n);
  (WORK.outline || []).forEach((o) => {
    if (o.no > written && !nos.includes(o.no)) nos.push(o.no);
  });
  nos.sort((a, b) => a - b);
  if (!nos.length) return;

  const sep = document.createElement("div");
  sep.className = "ch-plan-sep";
  sep.innerHTML = `예정 회차 <small>· 계획을 눌러 각 화 줄거리를 수정하세요 (지정한 내용대로 집필됩니다)</small>`;
  box.appendChild(sep);
  nos.forEach((n) => {
    const o = byNo[n];
    const el = document.createElement("div");
    el.className = "ch-item planned";
    el.innerHTML = `<span class="ch-no">${n}화</span>
      <span class="plan-body">
        ${o && o.title ? `<b>${escapeHtml(o.title)}</b>` : `<span class="dim">계획 미정 — 눌러서 작성</span>`}
        ${o && o.content ? `<small>${escapeHtml(o.content).slice(0, 70)}</small>` : ""}
      </span><span class="plan-edit">✎</span>`;
    el.onclick = () => editOutline(n, el);
    box.appendChild(el);
  });
}

function editOutline(n, el) {
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
  el.querySelector(".pe-cancel").onclick = () => renderChapters();
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
    renderChapters();
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
      await api(`/api/writer/works/${WORK.id}/canon/${encodeURIComponent(k)}`, { method: "DELETE" });
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

/* ---------- 회차 쓰기 ---------- */
$("#btn-write").onclick = async () => {
  const cpc = (WORK.chars_per_chapter || 5000).toLocaleString();
  busy(`${WORK.chapters.length + 1}화를 쓰는 중… (${cpc}자, 30초~1분)`);
  const r = await api(`/api/writer/works/${WORK.id}/chapters`, {
    method: "POST", body: JSON.stringify({ directive: $("#directive").value.trim() }),
  });
  unbusy();
  if (!r.ok) {
    notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : "") +
      (r.trace ? `\n${r.trace.join("\n")}` : ""));
    return;
  }
  $("#directive").value = "";
  await openWork(WORK.id);
  openChapter(r.id);
};

/* ---------- 편집기 ---------- */
async function openChapter(id) {
  const d = await api(`/api/writer/chapters/${id}`);
  if (!d.ok) { notice("회차를 불러오지 못했어요"); return; }
  CHAPTER = d.chapter;
  view("w-editor");
  const beat = WORK.beats[CHAPTER.beat_idx] || {};
  $("#ed-beat").textContent = `${CHAPTER.no}화 · 비트: ${beat.name || ""}`;
  $("#ed-title").value = CHAPTER.title || "";
  $("#ed-body").value = CHAPTER.body || "";
  // 삭제는 마지막 회차만 (중간을 비우면 기억이 끊긴다) — 아니면 버튼을 숨긴다
  const lastNo = WORK.chapters.length ? WORK.chapters[WORK.chapters.length - 1].no : 0;
  $("#ed-del").style.display = (CHAPTER.no === lastNo) ? "" : "none";
  countChars();
}
$("#ed-body").addEventListener("input", countChars);
function countChars() {
  $("#ed-count").textContent = `${$("#ed-body").value.length.toLocaleString()}자`;
}
$("#ed-back").onclick = () => openWork(WORK.id);
$("#ed-save").onclick = async () => {
  const r = await api(`/api/writer/chapters/${CHAPTER.id}`, {
    method: "PUT",
    body: JSON.stringify({ title: $("#ed-title").value, body: $("#ed-body").value }),
  });
  notice(r.ok ? "저장했어요." : r.error);
};
$("#ed-copy").onclick = async () => {
  await navigator.clipboard.writeText($("#ed-body").value);
  notice("본문을 복사했어요. 연재 플랫폼에 붙여넣으세요.");
};
$("#ed-download").onclick = () => {
  const blob = new Blob([`${$("#ed-title").value}\n\n${$("#ed-body").value}`],
    { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${WORK.title}_${CHAPTER.no}화.txt`;
  a.click();
};
$("#ed-regen").onclick = async () => {
  const directive = prompt("다시 쓸 때의 지시 (비워도 됩니다):", CHAPTER.directive || "");
  if (directive === null) return;
  busy("다시 쓰는 중…");
  const r = await api(`/api/writer/chapters/${CHAPTER.id}/regenerate`, {
    method: "POST", body: JSON.stringify({ directive }),
  });
  unbusy();
  if (!r.ok) { notice(r.error); return; }
  openChapter(CHAPTER.id);
};
$("#ed-del").onclick = async () => {
  if (!confirm("이 회차를 삭제할까요?")) return;
  const r = await api(`/api/writer/chapters/${CHAPTER.id}`, { method: "DELETE" });
  if (!r.ok) { notice(r.error); return; }
  openWork(WORK.id);
};

showHome();
