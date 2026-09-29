"""Textos para pegar en ChatGPT a partir de una transcripción."""
from __future__ import annotations

import re

from graba_reunion.groq_summary import truncate_transcript

PROMPT_KINDS = ("minutes", "cursor", "speakers")
SAMPLE_LIMIT = 3
SPEAKER_LABEL = re.compile(r"^SPEAKER_\d+$")
TIMED_LINE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s+\[([^\]]+)\]:\s*(.*)$")
PLAIN_LINE = re.compile(r"^\[([^\]]+)\]:\s*(.*)$")


def build_prompt(
    kind: str,
    transcript: str,
    title: str,
    recorded_at: str,
    *,
    minutes: str = "",
) -> str:
    if kind not in PROMPT_KINDS:
        raise ValueError(f"prompt desconocido: {kind}")
    body, _truncated = truncate_transcript(transcript)
    header = _header(title, recorded_at)
    if kind == "minutes":
        instruction = _minutes_instruction(minutes)
    elif kind == "cursor":
        instruction = _cursor_instruction()
    else:
        instruction = _speakers_instruction(transcript)
    return f"{header}\n\n{instruction}\n\nTranscripción:\n\n{body}\n"


def unidentified_samples(transcript: str, *, limit: int = SAMPLE_LIMIT) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for line in transcript.splitlines():
        speaker, text = _turn(line)
        if speaker is None or not SPEAKER_LABEL.match(speaker):
            continue
        samples = found.setdefault(speaker, [])
        if text and len(samples) < limit:
            samples.append(text)
    return found


def _header(title: str, recorded_at: str) -> str:
    lines = ["Reunión: " + (title.strip() or "(sin título)")]
    if recorded_at.strip():
        lines.append("Fecha: " + recorded_at.strip())
    return "\n".join(lines)


def _minutes_instruction(minutes: str) -> str:
    lines = [
        "Escribí una minuta en markdown, en español.",
        "Usá estas secciones, en este orden, y omití las que queden vacías:",
        "## Resumen",
        "## Temas tratados",
        "## Decisiones",
        "## Puntos de acción",
        "## Notas",
        "",
        "Cada punto de acción va así:",
        "- [ ] tarea (responsable: nombre; plazo: fecha)",
        "",
        "No inventes responsables ni plazos que no estén en la conversación.",
    ]
    existing = minutes.strip()
    if existing:
        lines.extend(
            [
                "",
                "Ya hay una minuta. Corregila: completá huecos y puntos de acción.",
                "No escribas otra de cero.",
                "",
                "Minuta actual:",
                "",
                existing,
            ]
        )
    return "\n".join(lines)


def _cursor_instruction() -> str:
    return "\n".join(
        [
            "Redactá un único prompt listo para pegar en Cursor.",
            "Tiene que decir qué hay que hacer según esta reunión,",
            "con las decisiones, los nombres y las restricciones que salieron.",
            "No implementes nada. No expliques el prompt. Devolvé solo el texto para pegar.",
        ]
    )


def _speakers_instruction(transcript: str) -> str:
    samples = unidentified_samples(transcript)
    if not samples:
        return "\n".join(
            [
                "No hay etiquetas SPEAKER_XX en esta transcripción.",
                "Revisá si algún nombre propio está mal asignado",
                "y decí en qué frases se nota.",
            ]
        )
    lines = [
        "Estas etiquetas todavía no tienen nombre.",
        "Decí quién parece ser cada una, según cómo la nombran los demás y de qué habla.",
        "Si no se puede saber, decilo.",
        "",
    ]
    for label, phrases in samples.items():
        lines.append(label)
        for phrase in phrases:
            lines.append(f"- {phrase}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _turn(line: str) -> tuple[str | None, str]:
    stripped = line.strip()
    timed = TIMED_LINE.match(stripped)
    if timed:
        return timed.group(1).strip(), timed.group(2).strip()
    plain = PLAIN_LINE.match(stripped)
    if plain:
        return plain.group(1).strip(), plain.group(2).strip()
    return None, ""
