"""Streamlit 재실행에서도 같은 asyncio 루프를 유지하는 사용자별 런타임."""

import asyncio

from .agent import ChatSession
from .config import Settings
from .experiments import BaselineSession


class SessionRuntime:
    def __init__(self, settings: Settings, mode="agent", search_mode="hybrid"):
        self.runner = asyncio.Runner()
        self.closed = False

        async def create():
            if mode == "agent":
                return ChatSession(settings)
            return BaselineSession(settings, mode=mode, search_mode=search_mode)

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
