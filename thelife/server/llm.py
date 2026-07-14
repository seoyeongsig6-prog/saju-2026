"""LLM 레이어 — GEMINI_API_KEY가 있으면 실제 모델, 없으면 목업 텍스트로 동작."""
import os
import time
from typing import Generator, Optional


class LLM:
    def __init__(self) -> None:
        self.key: Optional[str] = os.environ.get("GEMINI_API_KEY")
        self.model = None
        if self.key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.key)
                self.model = genai.GenerativeModel("gemini-2.0-flash")
            except Exception:
                self.model = None

    @property
    def is_mock(self) -> bool:
        return self.model is None

    def write(self, prompt: str, mock_text: str) -> str:
        if self.model is not None:
            try:
                text = self.model.generate_content(prompt).text
                if text and text.strip():
                    return text.strip()
            except Exception:
                pass
        return mock_text

    def stream(self, prompt: str, mock_text: str) -> Generator[str, None, None]:
        if self.model is not None:
            try:
                for chunk in self.model.generate_content(prompt, stream=True):
                    if chunk.text:
                        yield chunk.text
                return
            except Exception:
                pass
        for line in mock_text.splitlines(keepends=True):
            time.sleep(0.35)  # 스트리밍 체감용
            yield line


llm = LLM()
