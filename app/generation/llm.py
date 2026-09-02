"""Chat completion client. Depends on the ChatClient protocol, not on Ollama
directly, so a different local model server can be swapped in later.
"""
from typing import Protocol

import ollama


class ChatMessage:
    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class ChatClient(Protocol):
    def complete(self, messages: list[ChatMessage]) -> str: ...


class OllamaChatClient:
    def __init__(self, model: str, host: str) -> None:
        self._client = ollama.Client(host=host)
        self._model = model

    def complete(self, messages: list[ChatMessage]) -> str:
        response = self._client.chat(
            model=self._model,
            messages=[m.to_dict() for m in messages],
            options={"temperature": 0.1},
        )
        return response["message"]["content"]
