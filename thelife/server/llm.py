"""판매 앱의 Gemini LLM 레이어. GEMINI_API_KEY가 없으면 목업 텍스트로 동작한다.

모델이 퇴역(404)해도 서비스가 죽지 않도록 여러 후보 모델을 순서대로 시도한다.
"""
import os
import time
from typing import Generator, Optional

# Gemini 후보 — 앞에서부터 시도하고, 퇴역/미지원이면 다음으로 넘어간다.
# 환경변수 GEMINI_MODEL로 맨 앞에 원하는 모델을 지정할 수 있다.
GEMINI_CANDIDATES = [
    m for m in [
        os.environ.get("GEMINI_MODEL", "").strip(),
        "gemini-3.6-flash",
        "gemini-3.7-flash",
    ] if m
]

def _is_model_missing(err: str) -> bool:
    e = err.lower()
    return ("not found" in e or "not_found" in e or "404" in e
            or "no longer available" in e or "is not supported" in e
            or "unsupported" in e)


def _gemini_text(resp) -> str:
    """response.text 지름길 대신 응답 내부를 안전하게 꺼낸다.
    안전필터/토큰한도(finish_reason)로 .text가 예외를 던지는 문제를 회피한다.
    후보는 있으나 텍스트가 없으면 빈 문자열을 돌려준다 (호출부가 finish_reason 처리)."""
    cands = getattr(resp, "candidates", None)
    if cands is not None:
        out = []
        for cand in cands:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) or []
            out += [getattr(p, "text", "") for p in parts if getattr(p, "text", "")]
        return "".join(out)
    # 후보 속성이 없는 다른 SDK 형태 — 지름길 시도
    try:
        return resp.text
    except Exception:
        return ""


def _finish_reason(resp) -> str:
    try:
        cand = (getattr(resp, "candidates", None) or [None])[0]
        return str(getattr(cand, "finish_reason", "") or "")
    except Exception:
        return ""


class LLM:
    def __init__(self) -> None:
        self.provider: Optional[str] = None
        self.genai = None             # google.genai Client
        self.gemini_model: Optional[str] = None
        self.last_error: str = ""

        if os.environ.get("GEMINI_API_KEY"):
            try:
                from google import genai
                self.genai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
                self.gemini_model = (GEMINI_CANDIDATES[0] if GEMINI_CANDIDATES
                                     else "gemini-3.6-flash")
                self.provider = "gemini"
            except Exception:
                self.genai = None

    @property
    def is_mock(self) -> bool:
        return self.provider is None

    # ---- Gemini: 모델 후보를 순회하며 호출 ----
    def _gemini_generate(self, prompt: str, max_tokens: int, stream: bool):
        # 최신 Flash도 추론에 출력 토큰을 쓰므로 넉넉히 준다 (최소 800, 최대 8192)
        from google.genai import types
        cfg = types.GenerateContentConfig(max_output_tokens=max(800, min(max_tokens, 8192)))
        tried = []
        # 현재 모델을 맨 앞에 두고, 나머지 후보를 뒤에 붙인다
        order = [self.gemini_model] + [m for m in GEMINI_CANDIDATES if m != self.gemini_model]
        last = ""
        for name in order:
            if name in tried:
                continue
            tried.append(name)
            try:
                if stream:
                    resp = self.genai.models.generate_content_stream(
                        model=name, contents=prompt, config=cfg)
                else:
                    resp = self.genai.models.generate_content(
                        model=name, contents=prompt, config=cfg)
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
            if self.provider == "gemini":
                resp = self._gemini_generate(prompt, max_tokens, stream=False)
                text = _gemini_text(resp)
                if text and text.strip():
                    return text.strip()
                fr = _finish_reason(resp)
                self.last_error = f"빈 응답 (finish_reason={fr})" if fr else "빈 응답"
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {str(e)[:200]}"
            print(f"[llm] 호출 실패: {type(e).__name__}", flush=True)
        return mock_text

    def stream(self, prompt: str, mock_text: str) -> Generator[str, None, None]:
        try:
            if self.provider == "gemini":
                got = False
                for chunk in self._gemini_generate(prompt, 4096, stream=True):
                    t = _gemini_text(chunk) if False else None  # 스트림 청크는 아래서 안전 처리
                    try:
                        t = chunk.text
                    except Exception:
                        t = "".join(
                            getattr(p, "text", "")
                            for cand in (getattr(chunk, "candidates", None) or [])
                            for p in (getattr(getattr(cand, "content", None), "parts", None) or [])
                        )
                    if t:
                        got = True
                        yield t
                if got:
                    return
        except Exception as e:
            print(f"[llm] 스트림 실패: {type(e).__name__}", flush=True)
        for line in mock_text.splitlines(keepends=True):
            time.sleep(0.35)  # 스트리밍 체감용
            yield line


llm = LLM()
