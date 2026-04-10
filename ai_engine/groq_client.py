"""
groq_client — Groq API: chat completions, vision, audio transcription, token tracking.
All AI calls go through this module. No business logic here, just API wrappers.
"""

import base64
import io
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Union

import requests
import config.settings as settings

logger = logging.getLogger(__name__)

GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
_token_tracker: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}


def _get_api_key() -> str:
    """Get Groq API key from settings DB first, then env var."""
    db_key = ""
    try:
        from database.sqlite_client import get_settings
        db_key = get_settings().get("groq_api_key", "")
    except Exception:
        pass
    return db_key or settings.GROQ_API_KEY


def _update_token_usage(usage: dict) -> None:
    """Track token usage across all API calls."""
    try:
        _token_tracker["prompt_tokens"] += int(usage.get("prompt_tokens", 0))
        _token_tracker["completion_tokens"] += int(usage.get("completion_tokens", 0))
    except (TypeError, ValueError):
        pass


def sanitize_output(text: str) -> str:
    """Clean AI output: remove code fences, trim whitespace, ensure valid UTF-8."""
    try:
        cleaned = re.sub(r"```[\w]*\n?", "", text)
        cleaned = re.sub(r"```", "", cleaned).strip()
        return cleaned.encode("utf-8", errors="replace").decode("utf-8")
    except Exception:
        return text.strip()


def get_token_usage() -> dict:
    """Return cumulative token usage stats."""
    return dict(_token_tracker)


# ════════════════════════════════════════════════════════════════════════════
# TEXT CHAT COMPLETIONS (for Rx generation, CME, Research, etc.)
# ════════════════════════════════════════════════════════════════════════════

def call_groq(messages: list, model: str = None, temp: float = 0.3, max_tokens: int = 4000) -> str:
    """
    Groq chat completions — accepts list of content items (text strings or PIL Images).
    Automatically converts images to base64 for multimodal input.
    Returns the assistant's text response (cleaned), or empty string on failure.
    Supports retry on rate limit (max 2 retries, 2s sleep).
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("Groq API key not configured.")
        return ""

    if model is None:
        model = settings.GROQ_MODEL

    url = f"{GROQ_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # Build messages — convert mixed content (text + images) to proper format
    groq_messages = []
    for item in messages:
        if isinstance(item, str):
            # Plain text
            if not groq_messages:
                groq_messages.append({"role": "system", "content": item})
            else:
                groq_messages.append({"role": "user", "content": item})
        elif hasattr(item, 'save'):
            # PIL Image — convert to base64
            try:
                buf = io.BytesIO()
                item.save(buf, format='JPEG', quality=85)
                img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                content = [
                    {"type": "text", "text": "Analyze this prescription image carefully. Extract patient name, vitals, complaints, medications, and advice."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
                groq_messages.append({"role": "user", "content": content})
            except Exception as e:
                logger.error("Image conversion error: %s", e)

    payload = {
        "model": model,
        "messages": groq_messages,
        "temperature": temp,
        "max_tokens": max_tokens,
    }

    last_status = 0
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            last_status = resp.status_code
            if resp.status_code == 429:
                logger.warning("Rate limit hit, retry %d/2 after 2s", attempt + 1)
                time.sleep(2)
                continue
            resp.raise_for_status()
            data = resp.json()
            _update_token_usage(data.get("usage", {}))
            return sanitize_output(data["choices"][0]["message"]["content"])
        except requests.exceptions.HTTPError as e:
            logger.error("Groq HTTP error (attempt %d): %s", attempt + 1, e)
        except (KeyError, IndexError) as e:
            logger.error("Groq response parse error: %s", e)
        except requests.exceptions.RequestException as e:
            logger.error("Groq request error (attempt %d): %s", attempt + 1, e)
        if last_status != 429:
            break
    return ""


# ════════════════════════════════════════════════════════════════════════════
# VISION — specifically for batch scan prescription reading
# ════════════════════════════════════════════════════════════════════════════

def call_groq_vision(image, context: str = "") -> str:
    """
    Call Groq vision model with a single image to read handwritten prescription.
    Returns extracted text from the image.
    """
    if not hasattr(image, 'save'):
        # It's a file-like object, convert to PIL Image
        try:
            from PIL import Image
            image = Image.open(image)
        except Exception:
            return ""

    messages = [
        f"""You are an expert Indian pharmacist reading handwritten prescriptions.
Extract ALL information from this prescription image.

Return in this EXACT JSON format (no markdown, no code fences, pure JSON):
{{"patient_name": "name or empty", "phone": "10 digits or empty", "vitals": "BP/HR/Sugar/Weight or empty", "fee": "amount or 0", "complaints": "chief complaints", "diagnosis": "diagnosis if visible", "medicines": "all medicines with doses, frequency, duration", "advice": "lifestyle/diet advice", "follow_up": "follow up instructions", "investigations": "lab tests if mentioned"}}
{f"Context: {context}" if context else ""}""",
        image
    ]
    return call_groq(messages, model=settings.VISION_MODEL, temp=0.1, max_tokens=2000)


def parse_ai_json(text: str) -> dict:
    """Parse AI response that should be JSON. Tolerates markdown fences."""
    if not text:
        return {}
    try:
        # Strip markdown fences
        cleaned = re.sub(r"```json?\s*", "", text)
        cleaned = re.sub(r"```", "", cleaned).strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        try:
            match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
    return {}


# ════════════════════════════════════════════════════════════════════════════
# AUDIO TRANSCRIPTION (Voice Scribe)
# ════════════════════════════════════════════════════════════════════════════

def call_whisper(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """
    Transcribe audio using Groq Whisper API.
    Accepts raw audio bytes and filename (for content-type detection).
    Returns transcribed text or empty string on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("Groq API key not configured for Whisper.")
        return ""

    url = f"{GROQ_BASE_URL}/audio/transcriptions"
    try:
        # Determine content type from filename
        ext = filename.lower().split('.')[-1] if '.' in filename else 'webm'
        mime_map = {
            'webm': 'audio/webm', 'wav': 'audio/wav', 'mp3': 'audio/mpeg',
            'm4a': 'audio/mp4', 'ogg': 'audio/ogg', 'mp4': 'audio/mp4',
        }
        content_type = mime_map.get(ext, 'audio/webm')

        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, audio_bytes, content_type)},
            data={"model": settings.WHISPER_MODEL},
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("text", "")
        return sanitize_output(text)
    except requests.exceptions.RequestException as e:
        logger.error("Whisper transcription error: %s", e)
    except (KeyError, ValueError) as e:
        logger.error("Transcription parse error: %s", e)
    return ""
