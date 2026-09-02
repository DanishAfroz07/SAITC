"""Chat completion client. AnswerGenerator depends on the ChatClient Protocol
below, not on Ollama specifically - swapping to vLLM or llama.cpp's OpenAI-
compatible server later means adding one new class here, not touching
generation logic.
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
