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

function view(id) {
  ["w-home", "w-create", "w-work", "w-editor"].forEach((v) =>
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
$("#w-new").onclick = () => view("w-create");

/* ---------- 새 작품 ---------- */
$("#c-go").onclick = async () => {
  const body = {
    genre: $("#c-genre").value.trim() || "현대 판타지",
    premise: $("#c-premise").value.trim(),
    ending: $("#c-ending").value.trim(),
    title: $("#c-title").value.trim(),
    style: $("#c-style").value.trim(),
    total_chapters: Number($("#c-total").value) || 25,
  };
  if (!body.premise || !body.ending) { notice("로그라인과 결말은 작가만 정할 수 있어요. 두 칸을 채워주세요."); return; }
  busy("설계도를 만드는 중… 인물, 관계도, 15비트 플롯 (20초쯤)");
  const r = await api("/api/writer/works", { method: "POST", body: JSON.stringify(body) });
  unbusy();
  if (!r.ok) {
    notice((r.error || "실패했어요") + (r.detail ? `\n\n[원인] ${r.detail}` : "") +
      (r.trace ? `\n${r.trace.join("\n")}` : ""));
    return;
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

function renderChapters() {
  const box = $("#ch-list");
  box.innerHTML = "";
  if (!WORK.chapters.length) {
    box.innerHTML = `<p class="hint">아직 첫 회차가 없어요. 아래 버튼으로 1화를 시작하세요.<br>
      지시 없이 쓰면 플롯 지도대로, 지시를 넣으면 그 방향으로 씁니다.</p>`;
  }
  WORK.chapters.forEach((ch) => {
    const el = document.createElement("button");
    el.className = "ch-item";
    const beat = WORK.beats[ch.beat_idx] || {};
    el.innerHTML = `<span class="ch-no">${ch.no}화</span> ${ch.title || ""}
      <small>${beat.name || ""}</small>`;
    el.onclick = () => openChapter(ch.id);
    box.appendChild(el);
  });
}

function renderBible() {
  $("#bible-chars").innerHTML = WORK.characters.map((c) => `
    <div class="b-char"><b>${c.name}</b><span class="arch">${c.archetype || ""}</span>
      <p>${c.role || ""}<br>욕망 — ${c.want || ""} · 결핍 — ${c.need || ""}<br>비밀 — ${c.secret || ""}</p>
    </div>`).join("");
  $("#bible-rels").innerHTML = WORK.relations.map((r) => `
    <div class="b-rel"><b>${r.a} ↔ ${r.b}</b> · ${r.type || ""} — ${r.tension || ""}</div>`).join("");
  const written = WORK.chapters.length;
  $("#bible-beats").innerHTML = WORK.beats.map((b, i) => {
    const lastBeat = written ? WORK.chapters[written - 1].beat_idx : -1;
    return `<div class="b-beat ${i <= lastBeat ? "done" : ""}">
      <span class="no">${i + 1}</span><b>${b.name}</b><span>${b.summary || ""}</span></div>`;
  }).join("");
}

/* ---------- 회차 쓰기 ---------- */
$("#btn-write").onclick = async () => {
  busy(`${WORK.chapters.length + 1}화를 쓰는 중… (5,000자, 30초~1분)`);
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
