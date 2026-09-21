"""Título y minuta estructurada vía Groq."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from graba_reunion.config import DEFAULT_GROQ_MODEL, load_settings

MAX_TRANSCRIPT_CHARS = 120_000


@dataclass(frozen=True)
class MeetingSummary:
    title: str
    minutes: str
    model: str


def load_groq_api_key() -> str:
    return load_settings().groq_api_key


def _minutes_locale(language: str) -> str:
    code = (language or "es").strip().lower().split("-")[0]
    return "es" if code == "es" else "en"


def truncate_transcript(
    text: str,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
    *,
    language: str = "es",
) -> tuple[str, bool]:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned, False
    head = max_chars // 2
    tail = max_chars - head - 40
    marker = (
        "[... transcripción truncada ...]"
        if _minutes_locale(language) == "es"
        else "[... transcript truncated ...]"
    )
    return (
        f"{cleaned[:head]}\n\n{marker}\n\n{cleaned[-tail:]}",
        True,
    )


def _format_minutes(data: dict[str, Any], *, language: str = "es") -> str:
    locale = _minutes_locale(language)
    if locale == "es":
        title = "# Minuta de reunión"
        labels = {
            "summary": "Resumen",
            "topics": "Temas tratados",
            "decisions": "Decisiones",
            "actions": "Puntos de acción",
            "notes": "Notas",
            "assignee": "responsable",
            "deadline": "plazo",
        }
    else:
        title = "# Meeting minutes"
        labels = {
            "summary": "Summary",
            "topics": "Topics",
            "decisions": "Decisions",
            "actions": "Action items",
            "notes": "Notes",
            "assignee": "owner",
            "deadline": "due",
        }

    lines: list[str] = [title, ""]

    summary = str(data.get("summary", "")).strip()
    if summary:
        lines.extend([f"## {labels['summary']}", "", summary, ""])

    topics = data.get("topics") or []
    if topics:
        lines.extend([f"## {labels['topics']}", ""])
        for topic in topics:
            lines.append(f"- {str(topic).strip()}")
        lines.append("")

    decisions = data.get("decisions") or []
    if decisions:
        lines.extend([f"## {labels['decisions']}", ""])
        for decision in decisions:
            lines.append(f"- {str(decision).strip()}")
        lines.append("")

    action_items = data.get("action_items") or []
    if action_items:
        lines.extend([f"## {labels['actions']}", ""])
        for item in action_items:
            if isinstance(item, dict):
                task = str(item.get("task", "")).strip()
                if not task:
                    continue
                assignee = str(item.get("assignee") or "").strip()
                deadline = str(item.get("deadline") or "").strip()
                suffix_parts = []
                if assignee:
                    suffix_parts.append(f"{labels['assignee']}: {assignee}")
                if deadline:
                    suffix_parts.append(f"{labels['deadline']}: {deadline}")
                suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""
                lines.append(f"- [ ] {task}{suffix}")
            else:
                text = str(item).strip()
                if text:
                    lines.append(f"- [ ] {text}")
        lines.append("")

    notes = str(data.get("notes", "")).strip()
    if notes:
        lines.extend([f"## {labels['notes']}", "", notes, ""])

    return "\n".join(lines).strip()


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("La respuesta de Groq no es un objeto JSON.")
    return parsed


def _system_prompt(language: str) -> str:
    locale = _minutes_locale(language)
    if locale == "es":
        return (
            "Sos un asistente que resume reuniones en español. "
            "Respondé únicamente con JSON válido, sin markdown ni texto extra. "
            "Esquema: "
            '{"title": "título breve (máx 80 caracteres)", '
            '"summary": "párrafo resumen", '
            '"topics": ["tema 1", "..."], '
            '"decisions": ["decisión 1", "..."], '
            '"action_items": [{"task": "...", "assignee": null, "deadline": null}], '
            '"notes": "opcional"}'
        )
    return (
        "You are an assistant that summarizes meetings in English. "
        "Respond only with valid JSON, no markdown or extra text. "
        "Schema: "
        '{"title": "short title (max 80 chars)", '
        '"summary": "summary paragraph", '
        '"topics": ["topic 1", "..."], '
        '"decisions": ["decision 1", "..."], '
        '"action_items": [{"task": "...", "assignee": null, "deadline": null}], '
        '"notes": "optional"}'
    )


def summarize_transcript(
    transcript: str,
    *,
    model: str = DEFAULT_GROQ_MODEL,
    api_key: str | None = None,
    language: str | None = None,
) -> MeetingSummary:
    settings = load_settings()
    key = (api_key or settings.groq_api_key).strip()
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY no configurado. Exportalo o definilo con: graba-reunion setup"
        )

    try:
        from groq import Groq
    except ImportError as e:
        raise RuntimeError(
            "Falta el paquete groq. Instalá el proyecto con: pip install -e ."
        ) from e

    lang = language or settings.whisperx_language or "es"
    body, truncated = truncate_transcript(
        transcript,
        max_chars=settings.groq_max_chars,
        language=lang,
    )
    if _minutes_locale(lang) == "es":
        truncation_note = (
            "\n\nNota: la transcripción fue truncada por longitud; priorizá lo más relevante."
            if truncated
            else ""
        )
        user_prefix = "Transcripción de la reunión:"
        fallback_title = "Reunión sin título"
    else:
        truncation_note = (
            "\n\nNote: the transcript was truncated for length; prioritize the most relevant parts."
            if truncated
            else ""
        )
        user_prefix = "Meeting transcript:"
        fallback_title = "Untitled meeting"

    client = Groq(api_key=key)
    completion = client.chat.completions.create(
        model=model,
        temperature=settings.groq_temperature,
        max_tokens=4096,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _system_prompt(lang)},
            {
                "role": "user",
                "content": f"{user_prefix}{truncation_note}\n\n{body}",
            },
        ],
    )

    raw = completion.choices[0].message.content or ""
    data = _extract_json_object(raw)
    title = str(data.get("title", "")).strip() or fallback_title
    if len(title) > 120:
        title = title[:117].rstrip() + "..."
    minutes = _format_minutes(data, language=lang)
    return MeetingSummary(title=title, minutes=minutes, model=model)
