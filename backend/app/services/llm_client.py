import base64
import json
import logging
import mimetypes
import os
import time
from typing import Any, Dict, Generator, List, Tuple

import httpx


logger = logging.getLogger(__name__)


class LLMClient:
    """Zhipu client implemented with SSE only."""

    def __init__(self):
        self.api_key = os.getenv("ZHIPU_API_KEY", "").strip()
        if not self.api_key:
            raise ValueError("ZHIPU_API_KEY is required when ANALYZER_PROVIDER=llm")

        self.api_url = os.getenv(
            "ZHIPU_API_URL",
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        ).strip()
        self.text_model = os.getenv("ZHIPU_TEXT_MODEL", "glm-4.7")
        self.vision_model = os.getenv("ZHIPU_VISION_MODEL", "glm-4.7")
        self.timeout = float(os.getenv("LLM_REQUEST_TIMEOUT", "60"))
        self.connect_timeout = float(os.getenv("LLM_CONNECT_TIMEOUT", "10"))
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "6000"))
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
        self.thinking_type = os.getenv("LLM_THINKING_TYPE", "disabled").strip()

    def chat_with_vision(self, system_prompt: str, user_content: List[Dict[str, Any]]) -> str:
        _, content = self._create_completion(
            model=self.vision_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        text = content.strip()
        if not text:
            raise ValueError("Vision response content must be text")
        return text

    def chat_with_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        _, content = self._create_completion(
            model=self.text_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        return self._parse_json_payload(content)

    def _create_completion(self, *, model: str, messages: List[Dict[str, Any]], **kwargs) -> Tuple[str, str]:
        retries = max(self.max_retries, 0)
        last_error = None
        for attempt in range(retries + 1):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "stream": True,
                }
                if self.thinking_type:
                    payload["thinking"] = {"type": self.thinking_type}
                payload.update(kwargs)
                logger.info(
                    "LLM request start (attempt=%d/%d, model=%s, url=%s)",
                    attempt + 1,
                    retries + 1,
                    model,
                    self.api_url,
                )
                return self._stream_chat_completion(payload)
            except Exception as exc:  # pragma: no cover - external network failure
                last_error = exc
                if attempt >= retries:
                    raise
                wait_seconds = 0.4 * (attempt + 1)
                logger.warning(
                    "LLM call failed (attempt=%d/%d), retrying in %.1fs: %s: %s",
                    attempt + 1,
                    retries + 1,
                    wait_seconds,
                    type(exc).__name__,
                    exc,
                )
                time.sleep(wait_seconds)
        raise RuntimeError("LLM call failed unexpectedly") from last_error

    def _make_client(self) -> httpx.Client:
        timeout = httpx.Timeout(connect=self.connect_timeout, read=self.timeout, write=self.timeout, pool=self.timeout)
        return httpx.Client(timeout=timeout)

    def _stream_chat_completion(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        headers = {
            "Authorization": "Bearer {0}".format(self.api_key),
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        reasoning_acc: List[str] = []
        content_acc: List[str] = []

        client = self._make_client()
        try:
            with client.stream(
                "POST",
                self.api_url,
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    try:
                        error_body = response.json()
                    except Exception:
                        error_body = response.text
                    logger.error(
                        "LLM HTTP error status=%s body=%s",
                        response.status_code,
                        self._truncate_text(error_body, 800),
                    )
                    raise RuntimeError("HTTP {0}: {1}".format(response.status_code, error_body))

                for data in self._iter_sse_events(response):
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}

                    reasoning_piece = self._normalize_content(delta.get("reasoning_content"))
                    if reasoning_piece:
                        reasoning_acc.append(reasoning_piece)

                    content_piece = self._normalize_content(delta.get("content"))
                    if content_piece:
                        content_acc.append(content_piece)

                    if not content_piece:
                        message = choice.get("message") or {}
                        message_piece = self._normalize_content(message.get("content"))
                        if message_piece:
                            content_acc.append(message_piece)
        finally:
            client.close()

        if not content_acc:
            logger.warning(
                "LLM stream completed with empty content (reasoning_len=%d, model=%s)",
                len("".join(reasoning_acc)),
                payload.get("model"),
            )

        return "".join(reasoning_acc), "".join(content_acc)

    @staticmethod
    def _iter_sse_events(response: Any) -> Generator[str, None, None]:
        for raw in response.iter_lines():
            if not raw:
                continue
            if isinstance(raw, bytes):
                line = raw.decode("utf-8", errors="ignore").strip()
            else:
                line = raw.strip()
            if line.startswith("data:"):
                yield line[5:].strip()

    @staticmethod
    def _normalize_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            return "".join(text_parts)
        if isinstance(content, dict):
            return content.get("text", "")
        return str(content)

    @staticmethod
    def _parse_json_payload(content: Any) -> Dict[str, Any]:
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise ValueError("JSON response is not a valid JSON string/object")

        text = content.strip()
        if not text:
            raise ValueError("JSON response is empty")

        used_extraction = False
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.info(
                "LLM JSON parse failed on raw text, trying object extraction (error=%s, content=%s)",
                exc,
                LLMClient._truncate_text(text, 300),
            )
            used_extraction = True
            parsed = json.loads(LLMClient._extract_json_object_text(text))

        decode_depth = 0
        while isinstance(parsed, str) and decode_depth < 2:
            nested_text = parsed.strip()
            if not nested_text:
                break
            decode_depth += 1
            try:
                parsed = json.loads(nested_text)
                continue
            except json.JSONDecodeError:
                parsed = json.loads(LLMClient._extract_json_object_text(nested_text))

        if decode_depth > 0 or used_extraction:
            logger.info(
                "LLM JSON parse recovered non-standard response (decode_depth=%d, used_extraction=%s)",
                decode_depth,
                used_extraction,
            )

        if not isinstance(parsed, dict):
            raise ValueError("JSON response top-level must be object")
        return parsed

    @staticmethod
    def _extract_json_object_text(text: str) -> str:
        left = text.find("{")
        right = text.rfind("}")
        if left == -1 or right == -1 or right <= left:
            raise ValueError("Cannot locate JSON object in model output")
        return text[left : right + 1]

    @staticmethod
    def _truncate_text(value: Any, max_len: int = 500) -> str:
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False)
            except Exception:
                text = str(value)
        if len(text) <= max_len:
            return text
        return "{0}...<truncated>".format(text[:max_len])

    @staticmethod
    def image_to_base64_url(file_path: str) -> str:
        max_bytes = int(os.getenv("LLM_MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
        file_size = os.path.getsize(file_path)
        if file_size > max_bytes:
            raise ValueError("Image file is too large for LLM multimodal request")

        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        with open(file_path, "rb") as file:
            encoded = base64.b64encode(file.read()).decode("utf-8")
        return "data:{0};base64,{1}".format(mime_type, encoded)
