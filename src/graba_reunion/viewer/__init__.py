"""Visor local / hub web. Escucha solo en 127.0.0.1."""
from __future__ import annotations

import json
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import urlopen

from graba_reunion.commands.voice_wizard import clip_for
from graba_reunion.config import data_dir, load_settings
from graba_reunion.media import MEDIA_TYPES, VIDEO_SUFFIXES
from graba_reunion.meetings import list_meetings
from graba_reunion.phrases import phrases_path
from graba_reunion.viewer import hub_api
from graba_reunion.viewer.prompts import PROMPT_KINDS, build_prompt
from graba_reunion.viewer.speakers import rename_meeting_speakers, unidentified_speakers

DEFAULT_PORT = 8765
PORT_SPAN = 20
STATIC_DIR = Path(__file__).resolve().parent
MAX_BODY_BYTES = hub_api.MAX_UPLOAD_BYTES


def view_command(
    binary: str,
    *,
    meeting_id: str = "",
    start: float | None = None,
    output_dir: Path | None = None,
    tab: str = "",
) -> list[str]:
    command = [binary, "view"]
    if output_dir is not None:
        command.extend(["-d", str(output_dir)])
    if meeting_id:
        command.extend(["--id", meeting_id])
    if start is not None:
        command.extend(["--t", f"{start:.3f}"])
    if tab:
        command.extend(["--tab", tab])
    return command


def viewer_url(
    port: int,
    meeting_id: str = "",
    start: float | None = None,
    tab: str = "",
) -> str:
    base = f"http://127.0.0.1:{port}/"
    query: list[str] = []
    if tab:
        query.append(f"tab={quote(tab)}")
    if meeting_id:
        query.append(f"id={quote(meeting_id)}")
    if start is not None:
        query.append(f"t={start:.3f}")
    if not query:
        return base
    return base + "?" + "&".join(query)


def meeting_catalog(directory: Path, *, prefix: str | None = None) -> list[dict]:
    active = prefix if prefix is not None else _session_prefix()
    catalog: list[dict] = []
    seen: set[Path] = set()
    for meeting in list_meetings(directory, prefix=active):
        seen.add(meeting.path.resolve())
        catalog.append(_summary(meeting.path, meeting.title, meeting.recorded_label))
    catalog.extend(_loose_rows(directory, seen))
    return catalog


def meeting_detail(directory: Path, meeting_id: str, *, prefix: str | None = None) -> dict | None:
    if not _safe_meeting_id(meeting_id):
        return None
    active = prefix if prefix is not None else _session_prefix()
    for meeting in list_meetings(directory, prefix=active):
        if meeting.path.stem == meeting_id:
            return _full(meeting.path, meeting.title, meeting.recorded_label)
    txt = directory / f"{meeting_id}.txt"
    if txt.is_file() and _media_for(txt) is not None:
        return _full(txt, _loose_title(txt), _recorded_label(txt))
    return None


def meeting_txt(directory: Path, meeting_id: str) -> Path | None:
    detail = meeting_detail(directory, meeting_id)
    if detail is None:
        return None
    path = directory / f"{meeting_id}.txt"
    return path if path.is_file() else None


def resolve_media(directory: Path, name: str) -> Path | None:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    path = (directory / name).resolve()
    if path.parent != directory.resolve():
        return None
    if path.suffix.lower() not in MEDIA_TYPES or not path.is_file():
        return None
    return path


def media_content_type(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def parse_byte_range(header: str, size: int) -> tuple[int, int] | None:
    if size <= 0 or not header.startswith("bytes="):
        return None
    spec = header.removeprefix("bytes=").split(",", 1)[0].strip()
    if "-" not in spec:
        return None
    raw_start, raw_end = spec.split("-", 1)
    if raw_start == "":
        if not raw_end.isdigit():
            return None
        length = int(raw_end)
        if length <= 0:
            return None
        return max(0, size - length), size - 1
    if not raw_start.isdigit():
        return None
    start = int(raw_start)
    if start >= size:
        return None
    if raw_end == "":
        return start, size - 1
    if not raw_end.isdigit():
        return None
    end = min(int(raw_end), size - 1)
    if end < start:
        return None
    return start, end


def listening_port(directory: Path) -> int | None:
    state = _read_state()
    if state is None or not server_responds(state[0]):
        return None
    if state[1] != directory.resolve():
        return None
    return state[0]


def server_responds(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return False
    # Exige hub=True para no reutilizar un visor viejo sin /api/search ni /api/voices.
    return (
        isinstance(payload, dict)
        and payload.get("ok") is True
        and payload.get("hub") is True
    )


def cmd_view(
    output_dir: Path,
    *,
    meeting_id: str = "",
    start: float | None = None,
    tab: str = "",
) -> int:
    if tab not in {"", "conversations", "search", "voices", "transcribe"}:
        tab = ""
    directory = output_dir.resolve()
    port = listening_port(directory)
    if port is None:
        httpd = bind_server(directory)
        port = int(httpd.server_address[1])
        _write_port(port, directory)
        url = viewer_url(port, meeting_id, start, tab=tab)
        print(url)
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
        try:
            httpd.serve_forever()
        finally:
            _clear_port(port)
        return 0
    url = viewer_url(port, meeting_id, start, tab=tab)
    print(url)
    webbrowser.open(url)
    return 0


def bind_server(directory: Path) -> ThreadingHTTPServer:
    handler = _handler(directory)
    last_error: OSError | None = None
    for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_SPAN):
        if server_responds(port):
            continue
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError as error:
            last_error = error
            continue
    if last_error is not None:
        raise last_error
    raise OSError("No hay un puerto libre para el visor")


class ViewerHandler(BaseHTTPRequestHandler):
    directory: Path = Path(".")
    static_dir: Path = STATIC_DIR
    _voices_lock = threading.Lock()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/health":
            self._json({"ok": True, "hub": True})
            return
        if route == "/api/meetings":
            self._json(meeting_catalog(self.directory))
            return
        if route == "/api/search":
            self._search(parsed.query)
            return
        if route == "/api/voices":
            self._json(hub_api.voices_get())
            return
        if route == "/api/voices/status":
            self._json(hub_api.voices_status())
            return
        if route == "/api/similar":
            with self._voices_lock:
                self._json(hub_api.similar_get())
            return
        if route.startswith("/clips/"):
            self._clip(unquote(route.removeprefix("/clips/")))
            return
        if "/prompts/" in route and route.startswith("/api/meetings/"):
            self._prompt(route)
            return
        if "/files/" in route and route.startswith("/api/meetings/"):
            self._meeting_file(route)
            return
        if route.startswith("/api/meetings/"):
            meeting_id = unquote(route.removeprefix("/api/meetings/"))
            if "/" in meeting_id:
                self.send_error(404)
                return
            detail = meeting_detail(self.directory, meeting_id)
            if detail is None:
                self.send_error(404)
                return
            self._json(detail)
            return
        if route.startswith("/media/"):
            media = resolve_media(self.directory, unquote(route.removeprefix("/media/")))
            if media is None:
                self.send_error(404)
                return
            self._send_file(media, media_content_type(media))
            return
        if route in ("/", "/index.html"):
            self._send_static("index.html", "text/html; charset=utf-8")
            return
        if route == "/app.js":
            self._send_static("app.js", "text/javascript; charset=utf-8")
            return
        if route == "/app.css":
            self._send_static("app.css", "text/css; charset=utf-8")
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/api/voices":
            self._voices_save()
            return
        if route == "/api/voices/merge":
            self._voices_merge()
            return
        if route == "/api/transcribe":
            self._transcribe_upload()
            return
        if route.startswith("/api/meetings/") and route.endswith("/speakers"):
            self._rename_speakers(route)
            return
        if route.startswith("/api/meetings/") and route.endswith("/minutes/groq"):
            self._minutes_groq(route)
            return
        if route.startswith("/api/meetings/") and route.endswith("/minutes"):
            self._minutes_put(route)
            return
        if route.startswith("/api/meetings/") and route.endswith("/phrases"):
            self._phrases(route)
            return
        self.send_error(404)

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        if route.startswith("/api/meetings/") and route.endswith("/minutes"):
            self._minutes_put(route)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _search(self, query: str) -> None:
        q, word, participant = hub_api.parse_search_query(query)
        try:
            rows = hub_api.search_hits(self.directory, q, word=word, participant=participant)
        except Exception as error:  # noqa: BLE001 - devolver mensaje al cliente
            self._json({"ok": False, "message": str(error)}, status=500)
            return
        self._json({"ok": True, "hits": rows})

    def _clip(self, name: str) -> None:
        clusters = hub_api.load_voice_clusters()
        clip = clip_for(clusters, name)
        if clip is None:
            self.send_error(404)
            return
        self._send_file(clip, "audio/wav")

    def _prompt(self, route: str) -> None:
        rest = unquote(route.removeprefix("/api/meetings/"))
        meeting_id, separator, kind = rest.partition("/prompts/")
        if not separator or not meeting_id or "/" in kind or kind not in PROMPT_KINDS:
            self.send_error(404)
            return
        detail = meeting_detail(self.directory, meeting_id)
        if detail is None:
            self.send_error(404)
            return
        text = build_prompt(
            kind,
            str(detail.get("text") or ""),
            str(detail.get("title") or ""),
            str(detail.get("recorded_at") or ""),
            minutes=str(detail.get("minutes") or ""),
        )
        self._plain(text)

    def _meeting_file(self, route: str) -> None:
        rest = unquote(route.removeprefix("/api/meetings/"))
        meeting_id, separator, kind = rest.partition("/files/")
        if not separator or not meeting_id or kind not in {"txt", "minutes"}:
            self.send_error(404)
            return
        txt = meeting_txt(self.directory, meeting_id)
        if txt is None:
            self.send_error(404)
            return
        if kind == "txt":
            self._send_file(txt, "text/plain; charset=utf-8", download_name=txt.name)
            return
        minutes = txt.with_name(f"{txt.stem}_minuta.md")
        if not minutes.is_file():
            self.send_error(404)
            return
        self._send_file(minutes, "text/markdown; charset=utf-8", download_name=minutes.name)

    def _voices_save(self) -> None:
        try:
            payload = hub_api.parse_json_body(self._read_body(hub_api.MAX_JSON_BYTES))
            raw_names = payload.get("names")
            if not isinstance(raw_names, dict):
                raise ValueError("falta names")
            with self._voices_lock:
                result = hub_api.voices_save(raw_names)
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, RuntimeError) as error:
            self._json({"ok": False, "message": str(error) or "No se pudo guardar."}, status=400)
            return
        self._json(result)

    def _voices_merge(self) -> None:
        try:
            payload = hub_api.parse_json_body(self._read_body(hub_api.MAX_JSON_BYTES))
            left_id = int(payload["left"])
            right_id = int(payload["right"])
            with self._voices_lock:
                result = hub_api.voices_merge(left_id, right_id, str(payload.get("name") or ""))
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError, RuntimeError) as error:
            self._json({"ok": False, "message": str(error) or "No se pudo unir."}, status=400)
            return
        self._json(result)

    def _rename_speakers(self, route: str) -> None:
        meeting_id = unquote(route.removeprefix("/api/meetings/").removesuffix("/speakers"))
        txt = meeting_txt(self.directory, meeting_id)
        if txt is None:
            self.send_error(404)
            return
        try:
            payload = hub_api.parse_json_body(self._read_body(hub_api.MAX_JSON_BYTES))
            mapping = payload.get("names")
            if not isinstance(mapping, dict):
                raise ValueError("falta names")
            result = rename_meeting_speakers(txt, {str(k): str(v) for k, v in mapping.items()})
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, OSError) as error:
            self._json({"ok": False, "message": str(error) or "No se pudo renombrar."}, status=400)
            return
        self._json(result)

    def _minutes_put(self, route: str) -> None:
        meeting_id = unquote(route.removeprefix("/api/meetings/").removesuffix("/minutes"))
        txt = meeting_txt(self.directory, meeting_id)
        if txt is None:
            self.send_error(404)
            return
        try:
            payload = hub_api.parse_json_body(self._read_body(hub_api.MAX_JSON_BYTES))
            markdown = str(payload.get("markdown") or payload.get("text") or "")
            if not markdown.strip():
                raise ValueError("La minuta está vacía.")
            path = hub_api.write_minutes(txt, markdown)
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, OSError) as error:
            self._json({"ok": False, "message": str(error) or "No se pudo guardar."}, status=400)
            return
        self._json({"ok": True, "path": path.name, "message": "Minuta guardada."})

    def _minutes_groq(self, route: str) -> None:
        meeting_id = unquote(
            route.removeprefix("/api/meetings/").removesuffix("/minutes/groq")
        )
        txt = meeting_txt(self.directory, meeting_id)
        if txt is None:
            self.send_error(404)
            return
        media = _media_for(txt)
        try:
            path = hub_api.generate_minutes(txt, media)
            body = path.read_text(encoding="utf-8", errors="replace")
        except Exception as error:  # noqa: BLE001
            self._json({"ok": False, "message": str(error)}, status=400)
            return
        self._json({"ok": True, "minutes": body, "message": "Minuta generada."})

    def _phrases(self, route: str) -> None:
        meeting_id = unquote(route.removeprefix("/api/meetings/").removesuffix("/phrases"))
        txt = meeting_txt(self.directory, meeting_id)
        if txt is None:
            self.send_error(404)
            return
        media = _media_for(txt)
        if media is None:
            self._json({"ok": False, "message": "No hay media para regenerar frases."}, status=400)
            return
        try:
            hub_api.regenerate_phrases(self.directory, media)
        except Exception as error:  # noqa: BLE001
            self._json({"ok": False, "message": str(error)}, status=500)
            return
        self._json({"ok": True, "message": "Frases regeneradas."})

    def _transcribe_upload(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json({"ok": False, "message": "Cuerpo inválido o demasiado grande."}, status=400)
            return
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type") or ""
        try:
            files = hub_api.extract_multipart_files(content_type, body)
            ids = hub_api.transcribe_uploads(self.directory, files)
        except Exception as error:  # noqa: BLE001
            self._json({"ok": False, "message": str(error)}, status=400)
            return
        self._json({"ok": True, "ids": ids, "message": "Transcripción lista."})

    def _read_body(self, limit: int) -> bytes:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > limit:
            raise ValueError("Cuerpo inválido o demasiado grande.")
        return self.rfile.read(length)

    def _plain(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, name: str, content_type: str) -> None:
        path = self.static_dir / name
        if not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(
        self,
        path: Path,
        content_type: str,
        *,
        download_name: str | None = None,
    ) -> None:
        size = path.stat().st_size
        start = 0
        end = size - 1 if size else 0
        status = 200
        range_header = self.headers.get("Range")
        if range_header and download_name is None:
            parsed = parse_byte_range(range_header, size)
            if parsed is None:
                self.send_error(416)
                return
            start, end = parsed
            status = 206
        length = 0 if size == 0 else end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if download_name:
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{download_name}"',
            )
        else:
            self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return


def _handler(directory: Path) -> type[ViewerHandler]:
    static_dir = STATIC_DIR

    class BoundHandler(ViewerHandler):
        pass

    BoundHandler.directory = directory
    BoundHandler.static_dir = static_dir
    return BoundHandler


def _full(txt: Path, title: str, recorded_at: str) -> dict:
    summary = _summary(txt, title, recorded_at)
    media = _media_for(txt)
    summary["audio"] = f"/media/{quote(media.name)}" if media is not None else ""
    summary["text"] = txt.read_text(encoding="utf-8", errors="replace")
    minutes = txt.with_name(f"{txt.stem}_minuta.md")
    summary["minutes"] = (
        minutes.read_text(encoding="utf-8", errors="replace") if minutes.is_file() else ""
    )
    summary["phrases"] = _read_phrases(txt)
    summary["speakers"] = unidentified_speakers(summary["text"])
    return summary


def _summary(txt: Path, title: str, recorded_at: str) -> dict:
    media = _media_for(txt)
    minutes = txt.with_name(f"{txt.stem}_minuta.md")
    return {
        "id": txt.stem,
        "title": title,
        "recorded_at": recorded_at,
        "has_phrases": phrases_path(txt).is_file(),
        "has_minutes": minutes.is_file(),
        "has_audio": media is not None,
        "media_kind": _media_kind(media),
    }


def _loose_rows(directory: Path, seen: set[Path]) -> list[dict]:
    if not directory.is_dir():
        return []
    found: list[Path] = []
    for path in directory.glob("*.txt"):
        if not path.is_file() or path.resolve() in seen:
            continue
        if _media_for(path) is None:
            continue
        found.append(path)
    found.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [_summary(path, _loose_title(path), _recorded_label(path)) for path in found]


def _media_kind(media: Path | None) -> str:
    if media is not None and media.suffix.lower() in VIDEO_SUFFIXES:
        return "video"
    return "audio"


def _media_for(txt: Path) -> Path | None:
    for suffix in MEDIA_TYPES:
        candidate = txt.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def _loose_title(txt: Path) -> str:
    minutes = txt.with_name(f"{txt.stem}_minuta.md")
    if minutes.is_file():
        for line in minutes.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading
    return txt.stem


def _recorded_label(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _safe_meeting_id(meeting_id: str) -> bool:
    if not meeting_id or meeting_id in {".", ".."}:
        return False
    return "/" not in meeting_id and "\\" not in meeting_id and "\x00" not in meeting_id


def _read_phrases(txt: Path) -> dict | None:
    path = phrases_path(txt)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _session_prefix() -> str:
    return load_settings().session_prefix or "reunion"


def _state_path() -> Path:
    return data_dir() / "view-server.json"


def _read_state() -> tuple[int, Path] | None:
    path = _state_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    port = payload.get("port")
    raw_directory = payload.get("directory")
    if not isinstance(port, int) or port <= 0 or not isinstance(raw_directory, str):
        return None
    return port, Path(raw_directory).resolve()


def _write_port(port: int, directory: Path) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"port": port, "directory": str(directory.resolve())}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _clear_port(port: int) -> None:
    state = _read_state()
    if state is None or state[0] != port:
        return
    try:
        _state_path().unlink()
    except OSError:
        return
