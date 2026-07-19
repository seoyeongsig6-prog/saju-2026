"""LLM 레이어 — ANTHROPIC_API_KEY(Claude) 또는 GEMINI_API_KEY(Gemini)가 있으면
실제 모델로, 둘 다 없으면 목업 텍스트로 동작한다. Claude 키가 우선."""
import os
import time
from typing import Generator, Optional

CLAUDE_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-5")
GEMINI_MODEL = "gemini-2.0-flash"


PREFER = os.environ.get("LLM_PROVIDER", "").strip().lower()  # "gemini"면 무료 등급 우선


class LLM:
    def __init__(self) -> None:
        self.provider: Optional[str] = None
        self.client = None
        self.last_error: str = ""

        if PREFER != "gemini" and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.client = anthropic.Anthropic()
                self.provider = "anthropic"
            except Exception:
                self.client = None

        if self.client is None and os.environ.get("GEMINI_API_KEY"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.environ["GEMINI_API_KEY"])
                self.client = genai.GenerativeModel(GEMINI_MODEL)
                self.provider = "gemini"
            except Exception:
                self.client = None

    @property
    def is_mock(self) -> bool:
        return self.client is None

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
                text = self.client.generate_content(
                    prompt, generation_config={"max_output_tokens": min(max_tokens, 8192)},
                ).text
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
                for chunk in self.client.generate_content(prompt, stream=True):
                    if chunk.text:
                        yield chunk.text
                return
        except Exception:
            pass
        for line in mock_text.splitlines(keepends=True):
            time.sleep(0.35)  # 스트리밍 체감용
            yield line


llm = LLM()
