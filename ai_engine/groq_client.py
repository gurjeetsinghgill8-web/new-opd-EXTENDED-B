"""groq_client — Groq API: chat completions, audio transcription, token tracking."""
import logging, re, time
from typing import Any, Dict
import requests
import config.settings as settings

logger = logging.getLogger(__name__)
GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
_token_tracker: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}


def _update_token_usage(usage: Dict[str, Any]) -> None:
    """Response se token count update karo tracker mein."""
    try:
        _token_tracker["prompt_tokens"] += int(usage.get("prompt_tokens", 0))
        _token_tracker["completion_tokens"] += int(usage.get("completion_tokens", 0))
    except (TypeError, ValueError):
        logger.warning("Token usage parse nahi ho paya: %s", usage)


def call_llm(system_prompt: str, user_prompt: str, model: str = "llama-3.1-70b-versatile") -> str:
    """Groq chat completions — rate-limit pe max 2 retries, 2s sleep."""
    url = f"{GROQ_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.3, "max_tokens": 2000,
    }
    last_status = 0
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            last_status = resp.status_code
            if resp.status_code == 429:
                logger.warning("Rate limit, retry %d/2 after 2s", attempt + 1)
                time.sleep(2)
                continue
            resp.raise_for_status()
            data = resp.json()
            _update_token_usage(data.get("usage", {}))
            return str(data["choices"][0]["message"]["content"])
        except requests.exceptions.HTTPError as e:
            logger.error("Groq HTTP error (attempt %d): %s", attempt + 1, e)
        except (KeyError, IndexError) as e:
            logger.error("Groq response parse error: %s", e)
        except requests.exceptions.RequestException as e:
            logger.error("Groq request error (attempt %d): %s", attempt + 1, e)
        if last_status != 429:
            break
    return ""


def transcribe_audio(audio_bytes: bytes, model: str = "whisper-large-v3") -> str:
    """Groq audio/transcriptions API se speech-to-text karo."""
    url = f"{GROQ_BASE_URL}/audio/transcriptions"
    try:
        resp = requests.post(
            url, headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            files={"file": ("audio.webm", audio_bytes, "audio/webm")},
            data={"model": model}, timeout=60,
        )
        resp.raise_for_status()
        return str(resp.json().get("text", ""))
    except requests.exceptions.RequestException as e:
        logger.error("Audio transcription error: %s", e)
    except (KeyError, ValueError) as e:
        logger.error("Transcription parse error: %s", e)
    return ""


def get_token_usage() -> dict:
    """Abhi tak ka token usage de do."""
    return dict(_token_tracker)


def sanitize_output(text: str) -> str:
    """Code fences hatao, whitespace trim karo, valid UTF-8 ensure karo."""
    try:
        cleaned = re.sub(r"```[\w]*\n?", "", text)
        cleaned = re.sub(r"```", "", cleaned).strip()
        return cleaned.encode("utf-8", errors="replace").decode("utf-8")
    except Exception as e:
        logger.error("Sanitization error: %s", e)
        return text.strip()
