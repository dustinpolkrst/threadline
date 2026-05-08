import json
import re
import urllib.error
import urllib.request

from django.conf import settings


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(Exception):
    def __init__(self, message, code="openrouter_error", status_code=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def ticket_analysis_schema():
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "threadline_ticket_ai_analysis",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary", "triage", "client_context", "solution_draft", "risks", "context_refs"],
                "properties": {
                    "summary": {"type": "string"},
                    "triage": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["priority", "tags", "confidence", "reasoning", "assignee_reason"],
                        "properties": {
                            "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent", ""]},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "reasoning": {"type": "string"},
                            "assignee_reason": {"type": "string"},
                        },
                    },
                    "client_context": {"type": "array", "items": {"type": "string"}},
                    "solution_draft": {"type": "string"},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "context_refs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["type", "id", "title"],
                            "properties": {
                                "type": {"type": "string"},
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }


def build_request_payload(ai_settings, messages, max_tokens=1200, structured=True):
    payload = {
        "model": ai_settings.model or "openrouter/auto",
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "metadata": {"workspace_id": str(ai_settings.workspace_id)},
    }
    if structured:
        payload["response_format"] = ticket_analysis_schema()
    if ai_settings.zdr_only:
        payload["provider"] = {"zdr": True}
    return payload


def send_chat_completion(ai_settings, messages, max_tokens=1200, structured=True):
    if not ai_settings.api_key:
        raise OpenRouterError("OpenRouter API key is not configured.", code="missing_api_key")
    payload = build_request_payload(ai_settings, messages, max_tokens=max_tokens, structured=structured)
    headers = {
        "Authorization": f"Bearer {ai_settings.api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": getattr(settings, "OPENROUTER_SITE_URL", "https://threadline.local"),
        "X-OpenRouter-Title": getattr(settings, "OPENROUTER_APP_TITLE", "Threadline"),
    }
    request = urllib.request.Request(OPENROUTER_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=getattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 45)) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OpenRouterError(detail or str(exc), code=_code_for_status(exc.code), status_code=exc.code) from exc
    except urllib.error.URLError as exc:
        raise OpenRouterError(str(exc.reason), code="network_error") from exc
    except TimeoutError as exc:
        raise OpenRouterError("OpenRouter request timed out.", code="timeout") from exc


def parse_analysis_response(response):
    content = ""
    try:
        choice = response["choices"][0]
        if choice.get("finish_reason") == "length":
            preview = _safe_preview((choice.get("message") or {}).get("content") or "")
            raise OpenRouterError(
                f"The model response was truncated before valid JSON completed. Try a shorter context or increase max output tokens. Preview: {preview}",
                code="truncated_output",
            )
        message = choice["message"]
        parsed = _parse_message_payload(message)
    except OpenRouterError:
        raise
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        preview = _safe_preview(content or _message_content_preview(response))
        raise OpenRouterError(f"OpenRouter returned malformed analysis JSON. Preview: {preview}", code="malformed_json") from exc
    usage = response.get("usage") or {}
    return parsed, {
        "raw_model": response.get("model", ""),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def _parse_message_payload(message):
    for key in ["parsed", "structured", "json"]:
        value = message.get(key)
        if isinstance(value, dict):
            return value
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    if isinstance(content, dict):
        return content
    return json.loads(_extract_json_object(str(content)))


def _extract_json_object(content):
    cleaned = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = cleaned.find("{")
    if start < 0:
        return cleaned
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return cleaned[start : index + 1]
    return cleaned[start:]


def _message_content_preview(response):
    try:
        return response["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def _safe_preview(content):
    text = str(content).replace("\n", " ").strip()
    return text[:300] or "empty response"


def _code_for_status(status_code):
    if status_code in [401, 403]:
        return "auth_error"
    if status_code == 429:
        return "quota_or_rate_limit"
    if status_code in [400, 404]:
        return "routing_or_request_error"
    if status_code >= 500:
        return "provider_unavailable"
    return "openrouter_http_error"
