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


def truncate_transcript(text: str, max_chars: int = MAX_TRANSCRIPT_CHARS) -> tuple[str, bool]:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned, False
    head = max_chars // 2
    tail = max_chars - head - 40
    return (
        f"{cleaned[:head]}\n\n[... transcripción truncada ...]\n\n{cleaned[-tail:]}",
        True,
    )


def _format_minutes(data: dict[str, Any]) -> str:
    lines: list[str] = ["# Minuta de reunión", ""]

    summary = str(data.get("summary", "")).strip()
    if summary:
        lines.extend(["## Resumen", "", summary, ""])

    topics = data.get("topics") or []
    if topics:
        lines.extend(["## Temas tratados", ""])
        for topic in topics:
            lines.append(f"- {str(topic).strip()}")
        lines.append("")

    decisions = data.get("decisions") or []
    if decisions:
        lines.extend(["## Decisiones", ""])
        for decision in decisions:
            lines.append(f"- {str(decision).strip()}")
        lines.append("")

    action_items = data.get("action_items") or []
    if action_items:
        lines.extend(["## Puntos de acción", ""])
        for item in action_items:
            if isinstance(item, dict):
                task = str(item.get("task", "")).strip()
                if not task:
                    continue
                assignee = str(item.get("assignee") or "").strip()
                deadline = str(item.get("deadline") or "").strip()
                suffix_parts = []
                if assignee:
                    suffix_parts.append(f"responsable: {assignee}")
                if deadline:
                    suffix_parts.append(f"plazo: {deadline}")
                suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""
                lines.append(f"- [ ] {task}{suffix}")
            else:
                text = str(item).strip()
                if text:
                    lines.append(f"- [ ] {text}")
        lines.append("")

    notes = str(data.get("notes", "")).strip()
    if notes:
        lines.extend(["## Notas", "", notes, ""])

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


def summarize_transcript(
    transcript: str,
    *,
    model: str = DEFAULT_GROQ_MODEL,
    api_key: str | None = None,
) -> MeetingSummary:
    key = (api_key or load_groq_api_key()).strip()
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY no configurado. Exportalo o definilo en .env en la raíz del proyecto."
        )

    try:
        from groq import Groq
    except ImportError as e:
        raise RuntimeError(
            "Falta el paquete groq. Instalá el proyecto con: pip install -e ."
        ) from e

    body, truncated = truncate_transcript(transcript)
    truncation_note = (
        "\n\nNota: la transcripción fue truncada por longitud; priorizá lo más relevante."
        if truncated
        else ""
    )

    client = Groq(api_key=key)
    completion = client.chat.completions.create(
        model=model,
        temperature=0.2,
        max_tokens=4096,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Sos un asistente que resume reuniones en español. "
                    "Respondé únicamente con JSON válido, sin markdown ni texto extra. "
                    "Esquema: "
                    '{"title": "título breve (máx 80 caracteres)", '
                    '"summary": "párrafo resumen", '
                    '"topics": ["tema 1", "..."], '
                    '"decisions": ["decisión 1", "..."], '
                    '"action_items": [{"task": "...", "assignee": null, "deadline": null}], '
                    '"notes": "opcional"}'
                ),
            },
            {
                "role": "user",
                "content": f"Transcripción de la reunión:{truncation_note}\n\n{body}",
            },
        ],
    )

    raw = completion.choices[0].message.content or ""
    data = _extract_json_object(raw)
    title = str(data.get("title", "")).strip() or "Reunión sin título"
    if len(title) > 120:
        title = title[:117].rstrip() + "..."
    minutes = _format_minutes(data)
    return MeetingSummary(title=title, minutes=minutes, model=model)
