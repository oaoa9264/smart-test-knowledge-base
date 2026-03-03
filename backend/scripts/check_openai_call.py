#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict

import httpx

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.openai_client import OpenAIClient


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        # Use values from the target env file as source of truth for this check script.
        os.environ[key] = value


def _mask_key(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "<empty>"
    if len(text) <= 8:
        return "*" * len(text)
    return "{0}...{1}".format(text[:4], text[-4:])


def _build_prompts() -> Dict[str, str]:
    system_prompt = (
        "You are a JSON-only assistant. Return a valid JSON object and nothing else."
    )
    user_prompt = (
        'Return {"status":"ok","provider":"openai","message":"connectivity_check"}'
    )
    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def _http_check_via_api_url(*, api_url: str, api_key: str, model: str, prompts: Dict[str, str], timeout: float):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompts["system_prompt"]},
            {"role": "user", "content": prompts["user_prompt"]},
        ],
        "max_tokens": 200,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    headers = {
        "Authorization": "Bearer {0}".format(api_key),
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(api_url, headers=headers, json=payload)

    if response.status_code != 200:
        try:
            body = response.json()
        except Exception:
            body = response.text
        raise RuntimeError("HTTP {0}: {1}".format(response.status_code, body))

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("No choices in HTTP response")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if content is None:
        raise ValueError("No message.content in HTTP response")

    return OpenAIClient._parse_json_payload(content)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send a minimal JSON request through OpenAIClient to verify connectivity."
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to env file (default: backend/.env when run from backend).",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    api_url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions").strip()
    model = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.3-codex").strip()

    if base_url:
        print("[check] OPENAI_BASE_URL={0}".format(base_url))
    print("[check] OPENAI_API_URL={0}".format(api_url))
    print("[check] OPENAI_TEXT_MODEL={0}".format(model))
    print("[check] OPENAI_API_KEY={0}".format(_mask_key(api_key)))

    if not api_key:
        print("[error] OPENAI_API_KEY is empty. Please configure backend/.env first.")
        return 2

    prompts = _build_prompts()
    try:
        client = OpenAIClient()
        payload = client.chat_with_json(
            system_prompt=prompts["system_prompt"],
            user_prompt=prompts["user_prompt"],
        )
    except Exception as exc:
        print("[error] OpenAI call failed: {0}: {1}".format(type(exc).__name__, exc))
        return 1

    print("[ok] SDK call via OPENAI_BASE_URL succeeded.")
    print("[ok] SDK response JSON: {0}".format(json.dumps(payload, ensure_ascii=False)))

    try:
        payload_http = _http_check_via_api_url(
            api_url=api_url,
            api_key=api_key,
            model=model,
            prompts=prompts,
            timeout=float(os.getenv("LLM_REQUEST_TIMEOUT", "60")),
        )
    except Exception as exc:
        print("[error] HTTP call via OPENAI_API_URL failed: {0}: {1}".format(type(exc).__name__, exc))
        return 1

    print("[ok] HTTP call via OPENAI_API_URL succeeded.")
    print("[ok] HTTP response JSON: {0}".format(json.dumps(payload_http, ensure_ascii=False)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
