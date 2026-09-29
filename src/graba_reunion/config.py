"""Configuración centralizada desde variables de entorno y .env."""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu124"
DEFAULT_SESSION_PREFIX = "reunion"
DEFAULT_GROQ_MAX_CHARS = 120_000
DEFAULT_GROQ_TEMPERATURE = 0.2

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
    "GRABA_OUTPUT_DIR",
    "GRABA_SESSION_PREFIX",
    "GRABA_AUDIO_BACKEND",
    "GRABA_TORCH_INDEX",
    "GRABA_GROQ_MAX_CHARS",
    "GRABA_GROQ_TEMPERATURE",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def xdg_config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".config"


def xdg_data_home() -> Path:
    raw = os.environ.get("XDG_DATA_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".local" / "share"


def config_dir() -> Path:
    return xdg_config_home() / "graba-reunion"


def data_dir() -> Path:
    return xdg_data_home() / "graba-reunion"


def _resolve_graba_config_path() -> Path | None:
    raw = os.environ.get("GRABA_CONFIG", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_dir() or str(raw).endswith(("/", os.sep)):
        return path / ".env"
    if path.name == ".env" or path.suffix == ".env" or path.is_file():
        return path
    # Path that looks like a directory name but may not exist yet.
    if not path.suffix:
        return path / ".env"
    return path


def preferred_env_path() -> Path:
    """Ruta donde se escribe la config (XDG o GRABA_CONFIG)."""
    explicit = _resolve_graba_config_path()
    if explicit is not None:
        return explicit
    return config_dir() / ".env"


def project_env_path() -> Path:
    return project_root() / ".env"


def env_file_path() -> Path:
    """Ruta de lectura: preferida si existe; si no, fallback al .env del repo."""
    preferred = preferred_env_path()
    if preferred.is_file():
        return preferred
    if _resolve_graba_config_path() is not None:
        return preferred
    project_env = project_env_path()
    if project_env.is_file():
        return project_env
    return preferred


def torch_cuda_index() -> str:
    return (
        os.environ.get("GRABA_TORCH_INDEX", "").strip()
        or get_env_value("GRABA_TORCH_INDEX")
        or DEFAULT_TORCH_CUDA_INDEX
    )


# Compat: algunos módulos importan la constante.
TORCH_CUDA_INDEX = DEFAULT_TORCH_CUDA_INDEX


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


def _parse_int(raw: str, default: int) -> int:
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_float(raw: str, default: float) -> float:
    try:
        return float(raw)
    except ValueError:
        return default


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
    output_dir: str
    session_prefix: str
    audio_backend: str
    torch_index: str
    groq_max_chars: int
    groq_temperature: float

    @classmethod
    def load(cls) -> Settings:
        file_values = _parse_env_file(env_file_path())
        hf = get_env_value("HF_TOKEN", file_values=file_values) or get_env_value(
            "HUGGING_FACE_HUB_TOKEN", file_values=file_values
        )
        batch_size = _parse_int(
            get_env_value("GRABA_WHISPERX_BATCH_SIZE", file_values=file_values) or "16",
            16,
        )
        model = (
            get_env_value("GRABA_WHISPERX_MODEL", file_values=file_values)
            or get_env_value("GRABA_MODEL", file_values=file_values)
            or "large-v3"
        )
        language = (
            get_env_value("GRABA_WHISPERX_LANGUAGE", file_values=file_values)
            or get_env_value("GRABA_LANGUAGE", file_values=file_values)
            or "es"
        )
        device = get_env_value("GRABA_WHISPERX_DEVICE", file_values=file_values) or "cpu"
        compute_default = "float16" if device == "cuda" else "int8"
        compute_type = (
            get_env_value("GRABA_WHISPERX_COMPUTE_TYPE", file_values=file_values)
            or compute_default
        )
        backend = (
            get_env_value("GRABA_AUDIO_BACKEND", file_values=file_values) or "pulse"
        ).lower()
        if backend not in {"pulse", "alsa"}:
            backend = "pulse"
        groq_max_chars = _parse_int(
            get_env_value("GRABA_GROQ_MAX_CHARS", file_values=file_values)
            or str(DEFAULT_GROQ_MAX_CHARS),
            DEFAULT_GROQ_MAX_CHARS,
        )
        groq_temperature = _parse_float(
            get_env_value("GRABA_GROQ_TEMPERATURE", file_values=file_values)
            or str(DEFAULT_GROQ_TEMPERATURE),
            DEFAULT_GROQ_TEMPERATURE,
        )
        torch_index = (
            get_env_value("GRABA_TORCH_INDEX", file_values=file_values)
            or DEFAULT_TORCH_CUDA_INDEX
        )
        return cls(
            groq_api_key=get_env_value("GROQ_API_KEY", file_values=file_values),
            hf_token=hf,
            graba_mic=get_env_value("GRABA_MIC", file_values=file_values),
            graba_mon=get_env_value("GRABA_MON", file_values=file_values),
            groq_model=get_env_value("GRABA_GROQ_MODEL", file_values=file_values)
            or DEFAULT_GROQ_MODEL,
            whisperx_model=model,
            whisperx_language=language,
            whisperx_device=device,
            whisperx_compute_type=compute_type,
            whisperx_batch_size=batch_size,
            faster_whisper_model=model,
            faster_whisper_language=language,
            output_dir=get_env_value("GRABA_OUTPUT_DIR", file_values=file_values),
            session_prefix=get_env_value("GRABA_SESSION_PREFIX", file_values=file_values)
            or DEFAULT_SESSION_PREFIX,
            audio_backend=backend,
            torch_index=torch_index,
            groq_max_chars=groq_max_chars,
            groq_temperature=groq_temperature,
        )


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    return Settings.load()


def clear_settings_cache() -> None:
    load_settings.cache_clear()


def settings_with_overrides(
    settings: Settings,
    *,
    language: str | None = None,
    model: str | None = None,
    device: str | None = None,
) -> Settings:
    updates: dict[str, object] = {}
    if language:
        updates["whisperx_language"] = language
        updates["faster_whisper_language"] = language
    if model:
        updates["whisperx_model"] = model
        updates["faster_whisper_model"] = model
    if device:
        updates["whisperx_device"] = device
        if device == "cpu" and settings.whisperx_compute_type == "float16":
            updates["whisperx_compute_type"] = "int8"
        elif device == "cuda" and settings.whisperx_compute_type == "int8":
            updates["whisperx_compute_type"] = "float16"
    return replace(settings, **updates) if updates else settings


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


def write_env(updates: dict[str, str]) -> Path:
    """Escribe config en la ruta preferida; migra desde el .env del repo si hace falta."""
    target = preferred_env_path()
    project_env = project_env_path()
    migrated = False
    if (
        not target.is_file()
        and project_env.is_file()
        and target.resolve() != project_env.resolve()
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project_env, target)
        migrated = True
    else:
        target.parent.mkdir(parents=True, exist_ok=True)

    lines = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
    values = _parse_env_file(target) if target.is_file() else {}
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
    target.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    clear_settings_cache()
    if migrated:
        print(f"Configuración migrada a {target}")
    return target


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
