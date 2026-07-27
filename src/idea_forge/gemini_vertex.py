"""Vertex AI Gemini client used only by the Idea Forge pipeline."""

import json
import os
import time
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account


SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
PROJECT_ID = os.getenv("GEMINI_VERTEX_PROJECT_ID")
LOCATION = os.getenv("GEMINI_VERTEX_LOCATION", "global")
MODEL_ALIASES = {
    "gemini-pro": "gemini-3.1-pro-preview",
    "gemini-flash": "gemini-3.1-flash-lite-preview",
}
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def get_access_token():
    if not SERVICE_ACCOUNT_FILE:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS must point to a Vertex service-account JSON file."
        )

    credentials = service_account.Credentials.from_service_account_file(
        str(Path(SERVICE_ACCOUNT_FILE).expanduser()),
        scopes=SCOPES,
    )
    credentials.refresh(Request())
    return credentials.token


def call_gemini(
    prompt,
    *,
    model="gemini-flash",
    temperature=0.7,
    max_tokens=1024,
    timeout=120,
    retries=3,
):
    """Call Gemini through Vertex AI and return extracted response text."""
    if not PROJECT_ID:
        raise RuntimeError("GEMINI_VERTEX_PROJECT_ID must be set for Vertex Gemini calls.")

    vertex_model = MODEL_ALIASES.get(model, model)
    if LOCATION == "global":
        url = (
            "https://aiplatform.googleapis.com/v1/"
            f"projects/{PROJECT_ID}/locations/{LOCATION}/"
            f"publishers/google/models/{vertex_model}:generateContent"
        )
    else:
        url = (
            f"https://{LOCATION}-aiplatform.googleapis.com/v1/"
            f"projects/{PROJECT_ID}/locations/{LOCATION}/"
            f"publishers/google/models/{vertex_model}:generateContent"
        )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    for attempt in range(retries):
        try:
            headers = {
                "Authorization": f"Bearer {get_access_token()}",
                "Content-Type": "application/json",
            }
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return extract_text(response.json())
        except Exception as exc:
            if attempt == retries - 1:
                print(f"  [Gemini/Vertex/{vertex_model}] 调用失败: {exc}")
                return None
            time.sleep(5)

    return None


def extract_text(result):
    try:
        parts = result["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts).strip()
        return text or None
    except Exception:
        print(
            "  [Gemini/Vertex] 无法提取文本: "
            + json.dumps(result, ensure_ascii=False)[:500]
        )
        return None
