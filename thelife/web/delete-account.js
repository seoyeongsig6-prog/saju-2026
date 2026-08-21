const recovery = document.getElementById("recovery");
const agree = document.getElementById("agree");
const button = document.getElementById("delete");
const status = document.getElementById("status");
const apiBase = String(window.NOVELIST_API_BASE || "").replace(/\/$/, "");

function show(message, kind = "bad") {
  status.textContent = message;
  status.className = kind;
}

button.addEventListener("click", async () => {
  const code = recovery.value.trim();
  if (!code) return show("복구 코드를 입력해 주세요.");
  if (!agree.checked) return show("영구 삭제 안내를 확인해 주세요.");
  if (!window.confirm("계정과 모든 창작 데이터를 영구 삭제할까요? 이 작업은 되돌릴 수 없습니다.")) return;
  button.disabled = true;
  show("본인 확인 중이에요.", "");
  try {
    const authResponse = await fetch(apiBase + "/api/writer/auth/recover", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({recovery_code: code})
    });
    const auth = await authResponse.json();
    if (!auth.ok) throw new Error(auth.error || "복구 코드를 확인하지 못했어요.");
    const deletedResponse = await fetch(apiBase + "/api/writer/account", {
      method: "DELETE",
      headers: {"X-User-Id": auth.user_id, "X-Device-Token": auth.device_token}
    });
    const deleted = await deletedResponse.json();
    if (!deleted.ok) throw new Error(deleted.error || "삭제하지 못했어요.");
    recovery.value = ""; agree.checked = false;
    show("계정과 저장된 데이터가 삭제되었습니다.", "good");
  } catch (error) {
    show(error?.message || "잠시 후 다시 시도해 주세요.");
  } finally {
    button.disabled = false;
  }
});
