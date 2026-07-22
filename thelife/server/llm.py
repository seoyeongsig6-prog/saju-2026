"""LLM 레이어 — ANTHROPIC_API_KEY(Claude) 또는 GEMINI_API_KEY(Gemini)가 있으면
실제 모델로, 둘 다 없으면 목업 텍스트로 동작한다. LLM_PROVIDER=gemini면 Gemini 우선.

모델이 퇴역(404)해도 서비스가 죽지 않도록 여러 후보 모델을 순서대로 시도한다.
"""
import os
import time
from typing import Generator, Optional

CLAUDE_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-5")

# Gemini 후보 — 앞에서부터 시도하고, 퇴역/미지원이면 다음으로 넘어간다.
# 환경변수 GEMINI_MODEL로 맨 앞에 원하는 모델을 지정할 수 있다.
GEMINI_CANDIDATES = [
    m for m in [
        os.environ.get("GEMINI_MODEL", "").strip(),
        "gemini-2.5-flash",
        "gemini-2.0-flash-001",
        "gemini-flash-latest",
        "gemini-2.5-pro",
        "gemini-1.5-flash",
    ] if m
]

PREFER = os.environ.get("LLM_PROVIDER", "").strip().lower()  # "gemini"면 무료 등급 우선


def _is_model_missing(err: str) -> bool:
    e = err.lower()
    return ("not found" in e or "not_found" in e or "404" in e
            or "no longer available" in e or "is not supported" in e
            or "unsupported" in e)


class LLM:
    def __init__(self) -> None:
        self.provider: Optional[str] = None
        self.client = None            # anthropic 클라이언트
        self.genai = None             # google.generativeai 모듈
        self.gemini_model: Optional[str] = None
        self.last_error: str = ""

        if PREFER != "gemini" and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.client = anthropic.Anthropic()
                self.provider = "anthropic"
            except Exception:
                self.client = None

        if self.provider is None and os.environ.get("GEMINI_API_KEY"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.environ["GEMINI_API_KEY"])
                self.genai = genai
                self.gemini_model = (GEMINI_CANDIDATES[0] if GEMINI_CANDIDATES
                                     else "gemini-2.5-flash")
                self.provider = "gemini"
            except Exception:
                self.genai = None

    @property
    def is_mock(self) -> bool:
        return self.provider is None

    # ---- Gemini: 모델 후보를 순회하며 호출 ----
    def _gemini_generate(self, prompt: str, max_tokens: int, stream: bool):
        cfg = {"max_output_tokens": min(max_tokens, 8192)}
        tried = []
        # 현재 모델을 맨 앞에 두고, 나머지 후보를 뒤에 붙인다
        order = [self.gemini_model] + [m for m in GEMINI_CANDIDATES if m != self.gemini_model]
        last = ""
        for name in order:
            if name in tried:
                continue
            tried.append(name)
            try:
                model = self.genai.GenerativeModel(name)
                resp = model.generate_content(prompt, generation_config=cfg, stream=stream)
                self.gemini_model = name  # 성공한 모델을 기억
                return resp
            except Exception as e:
                last = f"{type(e).__name__}: {str(e)[:200]}"
                if _is_model_missing(last):
                    print(f"[llm] Gemini 모델 '{name}' 사용 불가 → 다음 후보 시도", flush=True)
                    continue
                raise
        raise RuntimeError(last or "사용 가능한 Gemini 모델이 없습니다")

    def write(self, prompt: str, mock_text: str, max_tokens: int = 1200) -> str:
        self.last_error = ""
        try:
            if self.provider == "anthropic":
                msg = self.client.messages.create(
                    model=CLAUDE_MODEL, max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = "".join(b.text for b in msg.content if b.type == "text")
                if text.strip():
                    return text.strip()
                self.last_error = "빈 응답"
            elif self.provider == "gemini":
                resp = self._gemini_generate(prompt, max_tokens, stream=False)
                text = resp.text
                if text and text.strip():
                    return text.strip()
                self.last_error = "빈 응답"
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"[llm] 호출 실패: {self.last_error}", flush=True)
        return mock_text

    def stream(self, prompt: str, mock_text: str) -> Generator[str, None, None]:
        try:
            if self.provider == "anthropic":
                with self.client.messages.stream(
                    model=CLAUDE_MODEL, max_tokens=1200,
                    messages=[{"role": "user", "content": prompt}],
                ) as s:
                    for text in s.text_stream:
                        yield text
                return
            elif self.provider == "gemini":
                for chunk in self._gemini_generate(prompt, 4096, stream=True):
                    if chunk.text:
                        yield chunk.text
                return
        except Exception as e:
            print(f"[llm] 스트림 실패: {type(e).__name__}: {str(e)[:150]}", flush=True)
        for line in mock_text.splitlines(keepends=True):
            time.sleep(0.35)  # 스트리밍 체감용
            yield line


llm = LLM()
