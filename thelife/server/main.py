"""Render의 기존 실행 명령을 위한 호환 진입점.

이 저장소의 배포 대상은 판매용 소설 앱이다. Render 대시보드에 예전
``uvicorn server.main:app`` 명령이 남아 있어도 게임 서버를 띄우지 않고
소설 앱 전용 ASGI 애플리케이션을 사용한다.
"""

from .novelist_main import app

__all__ = ["app"]
