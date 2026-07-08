"""Configuración centralizada desde variables de entorno y .env."""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu124"

ENV_KEYS = (
    "GROQ_API_KEY",
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "GRABA_MIC",
    "GRABA_MON",
    "GRABA_GROQ_MODEL",
    "GRABA_WHISPERX_MODEL",
    "GRABA_WHISPERX_LANGUAGE",
    "GRABA_WHISPERX_DEVICE",
    "GRABA_WHISPERX_COMPUTE_TYPE",
    "GRABA_WHISPERX_BATCH_SIZE",
    "GRABA_MODEL",
    "GRABA_LANGUAGE",
    "GRABA_DB",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def env_file_path() -> Path:
    return project_root() / ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        values[key.strip()] = raw.strip().strip('"').strip("'")
    return values


def get_env_value(key: str, *, file_values: dict[str, str] | None = None) -> str:
    direct = os.environ.get(key, "").strip()
    if direct:
        return direct
    file_vals = file_values if file_values is not None else _parse_env_file(env_file_path())
    return file_vals.get(key, "").strip()


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    hf_token: str
    graba_mic: str
    graba_mon: str
    groq_model: str
    whisperx_model: str
    whisperx_language: str
    whisperx_device: str
    whisperx_compute_type: str
    whisperx_batch_size: int
    faster_whisper_model: str
    faster_whisper_language: str
    graba_db: str

    @classmethod
    def load(cls) -> Settings:
        file_values = _parse_env_file(env_file_path())
        hf = get_env_value("HF_TOKEN", file_values=file_values) or get_env_value(
            "HUGGING_FACE_HUB_TOKEN", file_values=file_values
        )
        batch_raw = get_env_value("GRABA_WHISPERX_BATCH_SIZE", file_values=file_values) or "16"
        try:
            batch_size = int(batch_raw)
        except ValueError:
            batch_size = 16
        return cls(
            groq_api_key=get_env_value("GROQ_API_KEY", file_values=file_values),
            hf_token=hf,
            graba_mic=get_env_value("GRABA_MIC", file_values=file_values),
            graba_mon=get_env_value("GRABA_MON", file_values=file_values),
            groq_model=get_env_value("GRABA_GROQ_MODEL", file_values=file_values)
            or DEFAULT_GROQ_MODEL,
            whisperx_model=get_env_value("GRABA_WHISPERX_MODEL", file_values=file_values)
            or "large-v3",
            whisperx_language=get_env_value("GRABA_WHISPERX_LANGUAGE", file_values=file_values)
            or "es",
            whisperx_device=get_env_value("GRABA_WHISPERX_DEVICE", file_values=file_values)
            or "cuda",
            whisperx_compute_type=get_env_value(
                "GRABA_WHISPERX_COMPUTE_TYPE", file_values=file_values
            )
            or "float16",
            whisperx_batch_size=batch_size,
            faster_whisper_model=get_env_value("GRABA_MODEL", file_values=file_values)
            or "large-v3",
            faster_whisper_language=get_env_value("GRABA_LANGUAGE", file_values=file_values)
            or "es",
            graba_db=get_env_value("GRABA_DB", file_values=file_values),
        )


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    return Settings.load()


def clear_settings_cache() -> None:
    load_settings.cache_clear()


FLOW_REQUIRED: dict[str, tuple[str, ...]] = {
    "record": ("GRABA_MIC", "GRABA_MON"),
    "diarize": ("HF_TOKEN",),
    "groq": ("GROQ_API_KEY",),
    "fast": (),
}


def _field_value(settings: Settings, field: str) -> str:
    mapping = {
        "GROQ_API_KEY": settings.groq_api_key,
        "HF_TOKEN": settings.hf_token,
        "GRABA_MIC": settings.graba_mic,
        "GRABA_MON": settings.graba_mon,
    }
    return mapping.get(field, "").strip()


def missing_required_fields(flow: str) -> list[str]:
    settings = load_settings()
    missing: list[str] = []
    for field in FLOW_REQUIRED.get(flow, ()):
        if not _field_value(settings, field):
            missing.append(field)
    return missing


def is_configured(flow: str) -> bool:
    return not missing_required_fields(flow)


def write_env(updates: dict[str, str]) -> None:
    path = env_file_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    values = _parse_env_file(path) if path.is_file() else {}
    values.update({key: value for key, value in updates.items() if value is not None})
    known_keys = set(ENV_KEYS)
    output: list[str] = []
    written: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in values:
            output.append(f"{key}={values[key]}")
            written.add(key)
        else:
            output.append(line)
    for key in sorted(values):
        if key not in written and key in known_keys:
            output.append(f"{key}={values[key]}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    clear_settings_cache()


def resolve_whisperx_bin() -> Path | None:
    found = shutil.which("whisperx")
    if found:
        return Path(found)
    sibling = Path(sys.executable).parent / "whisperx"
    if sibling.is_file():
        return sibling
    local = project_root() / ".venv" / "bin" / "whisperx"
    if local.is_file():
        return local
    return None


def is_faster_whisper_importable() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def is_torch_cuda_available() -> bool | None:
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        return None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None
