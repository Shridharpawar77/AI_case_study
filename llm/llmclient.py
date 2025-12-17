import os
import base64
from typing import Any, Dict, List, Optional, Union

import requests
from dotenv import load_dotenv

load_dotenv()  # ✅ ensure env loaded before reading


# =========================
# Ollama configuration
# =========================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "minicpm-v")  # expected: minicpm-v


class OllamaClient:
    """
    Minimal client for Ollama /api/chat supporting text + vision (images).
    """

    def __init__(self, base_url: str, model: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    @staticmethod
    def _b64_image(image: Union[str, bytes]) -> str:
        """
        Accepts:
          - bytes: raw image bytes
          - str: path to an image file
        Returns base64-encoded string (no data URI prefix).
        """
        if isinstance(image, bytes):
            raw = image
        else:
            with open(image, "rb") as f:
                raw = f.read()
        return base64.b64encode(raw).decode("utf-8")

    def chat(
        self,
        messages: List[Dict[str, Any]],
        images: Optional[List[Union[str, bytes]]] = None,
        temperature: Optional[float] = None,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        messages format (Ollama style):
          [{"role":"system"|"user"|"assistant", "content":"..."}]

        For vision:
          - Pass images=[path_or_bytes,...]
          - Images will be attached to the LAST user message (typical pattern).
        """
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }

        merged_options: Dict[str, Any] = {}
        if options:
            merged_options.update(options)
        if temperature is not None:
            merged_options["temperature"] = temperature
        if merged_options:
            payload["options"] = merged_options

        if images:
            b64_images = [self._b64_image(img) for img in images]

            # Attach to the last user message; if none exists, create one.
            last_user_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    last_user_idx = i
                    break
            if last_user_idx is None:
                messages.append({"role": "user", "content": ""})
                last_user_idx = len(messages) - 1

            messages[last_user_idx]["images"] = b64_images

        url = f"{self.base_url}/api/chat"
        resp = requests.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def chat_text(
        self,
        messages: List[Dict[str, Any]],
        images: Optional[List[Union[str, bytes]]] = None,
        temperature: Optional[float] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Convenience: returns assistant text only.
        """
        data = self.chat(
            messages=messages,
            images=images,
            temperature=temperature,
            stream=False,
            options=options,
        )
        return (data.get("message") or {}).get("content", "")


# Keep these names simple for the rest of your app
client = OllamaClient(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL)
MODEL_NAME = OLLAMA_MODEL
