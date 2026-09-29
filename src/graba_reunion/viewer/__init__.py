"""Visor local de conversaciones. Escucha solo en 127.0.0.1."""
from __future__ import annotations

import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import urlopen

from graba_reunion.config import data_dir, load_settings
from graba_reunion.meetings import list_meetings
from graba_reunion.phrases import phrases_path
from graba_reunion.viewer.prompts import PROMPT_KINDS, build_prompt

DEFAULT_PORT = 8765
PORT_SPAN = 20
STATIC_DIR = Path(__file__).resolve().parent
_MEETING_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,200}$")


def view_command(binary: str, *, meeting_id: str = "", start: float | None = None) -> list[str]:
    command = [binary, "view"]
    if meeting_id:
        command.extend(["--id", meeting_id])
    if start is not None:
        command.extend(["--t", f"{start:.3f}"])
    return command


def viewer_url(port: int, meeting_id: str = "", start: float | None = None) -> str:
    base = f"http://127.0.0.1:{port}/"
    query: list[str] = []
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
    for meeting in list_meetings(directory, prefix=active):
        catalog.append(_summary(meeting.path, meeting.title, meeting.recorded_label))
    return catalog


def meeting_detail(directory: Path, meeting_id: str, *, prefix: str | None = None) -> dict | None:
    if not _MEETING_ID.match(meeting_id):
        return None
    active = prefix if prefix is not None else _session_prefix()
    for meeting in list_meetings(directory, prefix=active):
        if meeting.path.stem != meeting_id:
            continue
        summary = _summary(meeting.path, meeting.title, meeting.recorded_label)
        audio = meeting.path.with_suffix(".mp3")
        summary["audio"] = f"/media/{quote(audio.name)}" if audio.is_file() else ""
        summary["text"] = meeting.path.read_text(encoding="utf-8", errors="replace")
        minutes = meeting.minutes_path
        summary["minutes"] = (
            minutes.read_text(encoding="utf-8", errors="replace") if minutes is not None else ""
        )
        summary["phrases"] = _read_phrases(meeting.path)
        return summary
    return None


def resolve_media(directory: Path, name: str) -> Path | None:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    path = (directory / name).resolve()
    if path.parent != directory.resolve():
        return None
    if path.suffix.lower() != ".mp3" or not path.is_file():
        return None
    return path


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


def listening_port() -> int | None:
    stored = _read_port()
    if stored is not None and server_responds(stored):
        return stored
    if server_responds(DEFAULT_PORT):
        return DEFAULT_PORT
    return None


def server_responds(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("ok") is True


def cmd_view(output_dir: Path, *, meeting_id: str = "", start: float | None = None) -> int:
    directory = output_dir.resolve()
    port = listening_port()
    if port is None:
        httpd = bind_server(directory)
        port = int(httpd.server_address[1])
        _write_port(port)
        url = viewer_url(port, meeting_id, start)
        print(url)
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
        try:
            httpd.serve_forever()
        finally:
            _clear_port(port)
        return 0
    url = viewer_url(port, meeting_id, start)
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

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/health":
            self._json({"ok": True})
            return
        if route == "/api/meetings":
            self._json(meeting_catalog(self.directory))
            return
        if "/prompts/" in route and route.startswith("/api/meetings/"):
            self._prompt(route)
            return
        if route.startswith("/api/meetings/"):
            meeting_id = unquote(route.removeprefix("/api/meetings/"))
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
            self._send_file(media, "audio/mpeg")
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

    def log_message(self, format: str, *args: object) -> None:
        return

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

    def _plain(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
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

    def _send_file(self, path: Path, content_type: str) -> None:
        size = path.stat().st_size
        start = 0
        end = size - 1 if size else 0
        status = 200
        range_header = self.headers.get("Range")
        if range_header:
            parsed = parse_byte_range(range_header, size)
            if parsed is None:
                self.send_error(416)
                return
            start, end = parsed
            status = 206
        length = 0 if size == 0 else end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
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


def _summary(txt: Path, title: str, recorded_at: str) -> dict:
    audio = txt.with_suffix(".mp3")
    minutes = txt.with_name(f"{txt.stem}_minuta.md")
    return {
        "id": txt.stem,
        "title": title,
        "recorded_at": recorded_at,
        "has_phrases": phrases_path(audio).is_file(),
        "has_minutes": minutes.is_file(),
        "has_audio": audio.is_file(),
    }


def _read_phrases(txt: Path) -> dict | None:
    path = phrases_path(txt.with_suffix(".mp3"))
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


def _read_port() -> int | None:
    path = _state_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    port = payload.get("port") if isinstance(payload, dict) else None
    if isinstance(port, int) and port > 0:
        return port
    return None


def _write_port(port: int) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"port": port}), encoding="utf-8")


def _clear_port(port: int) -> None:
    if _read_port() != port:
        return
    try:
        _state_path().unlink()
    except OSError:
        return
