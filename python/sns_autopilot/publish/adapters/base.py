"""발행 어댑터 공통 인터페이스."""
from __future__ import annotations

import os
from typing import Any


class Adapter:
    name: str = ""
    #: 이 값들이 환경변수에 모두 있어야 "설정됨" 으로 봅니다.
    required_env: tuple[str, ...] = ()

    def configured(self) -> bool:
        return all(os.environ.get(key) for key in self.required_env)

    def send(self, post: dict, assets: dict, ctx: dict) -> dict[str, Any]:
        raise NotImplementedError
