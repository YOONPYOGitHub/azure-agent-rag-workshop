"""Streamlit 재실행에서도 같은 asyncio 루프를 유지하는 사용자별 런타임."""

import asyncio

from .agent import ChatSession
from .config import Settings


class SessionRuntime:
    def __init__(self, settings: Settings):
        self.runner = asyncio.Runner()
        self.closed = False

        async def create():
            return ChatSession(settings)

        self.chat = self.runner.run(create())

    def run(self, coroutine):
        return self.runner.run(coroutine)

    def close(self):
        if not self.closed:
            try:
                self.runner.run(self.chat.close())
            finally:
                self.runner.close()
                self.closed = True
