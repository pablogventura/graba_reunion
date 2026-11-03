"""Página local para escuchar voces nuevas y ponerles nombre."""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from graba_reunion.voice_enroll import save_review
from graba_reunion.voices import (
    MATCH_SIMILARITY,
    VoiceCluster,
    bank_from_names,
    cluster_display_name,
    format_duration,
    is_new_voice,
    load_voice_bank,
    merge_voice_banks,
    patch_names_file,
    profile_match_scores,
    save_voice_bank,
    voice_pair_scores,
    voices_dir,
    without_embeddings,
)

WIZARD_PORT = 8775
PORT_SPAN = 20
MAX_BODY_BYTES = 64_000

PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Voces nuevas</title>
  <style>
    :root {
      color: #1c1915; background: #f4f0e6;
      font-family: "Segoe UI", "Liberation Sans", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; }
    main { max-width: 720px; margin: 0 auto; padding: 24px 20px 64px; }
    h1 { font-size: 1.4rem; margin: 0 0 8px; }
    p { color: #5c564c; }
    article {
      background: #fffdf8; border: 1px solid #d5cdbc; border-radius: 10px;
      padding: 14px 16px; margin: 0 0 12px;
    }
    article h2 { font-size: 1rem; margin: 0 0 4px; }
    audio { width: 100%; margin: 8px 0; }
    label { display: block; font-size: 0.9rem; margin-top: 6px; }
    input {
      width: 100%; font: inherit; padding: 8px;
      border: 1px solid #d5cdbc; border-radius: 8px;
    }
    .row { display: flex; gap: 8px; margin-top: 8px; }
    button {
      font: inherit; padding: 8px 12px; border-radius: 8px;
      border: 1px solid #1c1915; background: #1c1915; color: #f4f0e6; cursor: pointer;
    }
    button.quiet { background: transparent; color: #1c1915; }
    #status { min-height: 1.4em; }
  </style>
</head>
<body>
  <main>
    <h1>Voces nuevas</h1>
    <p><a href="/parecidos">Ver parecidos entre voces</a></p>
    <p>Escuchá el clip y escribí el nombre. Si es alguien que ya está, usá el mismo nombre.
    Un guion la ignora (música o ruido). Vacío la deja para después.</p>
    <p>Los nombres valen para las próximas transcripciones. No reescriben los textos viejos.</p>
    <form id="form"></form>
    <p id="status"></p>
  </main>
  <script>
    const form = document.querySelector("#form");
    const status = document.querySelector("#status");
    fetch("/api/voices").then((response) => response.json()).then((payload) => {
      const list = document.createElement("datalist");
      list.id = "known";
      for (const name of payload.known_names) {
        const option = document.createElement("option");
        option.value = name;
        list.append(option);
      }
      form.append(list);
      if (!payload.voices.length) {
        status.textContent = "No hay voces nuevas.";
        return;
      }
      for (const voice of payload.voices) {
        form.append(card(voice));
      }
      const save = document.createElement("button");
      save.type = "submit";
      save.textContent = "Guardar";
      form.append(save);
    }).catch(() => {
      status.textContent = "No se pudo cargar la lista.";
    });

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const names = {};
      for (const input of form.querySelectorAll("input[data-id]")) {
        names[input.dataset.id] = input.value.trim();
      }
      status.textContent = "Guardando...";
      fetch("/api/voices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ names }),
      }).then((response) => response.json()).then((payload) => {
        status.textContent = payload.message || "Listo.";
      }).catch(() => {
        status.textContent = "No se pudo guardar.";
      });
    });

    function card(voice) {
      const article = document.createElement("article");
      const title = document.createElement("h2");
      title.textContent = voice.title;
      article.append(title);
      const where = document.createElement("p");
      where.textContent = voice.sources;
      article.append(where);
      if (voice.clip) {
        const audio = document.createElement("audio");
        audio.controls = true;
        audio.preload = "none";
        audio.src = voice.clip;
        article.append(audio);
      }
      const label = document.createElement("label");
      label.textContent = "Nombre";
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.id = String(voice.id);
      input.setAttribute("list", "known");
      label.append(input);
      article.append(label);
      const ignore = document.createElement("button");
      ignore.type = "button";
      ignore.className = "quiet";
      ignore.textContent = "Ignorar";
      ignore.addEventListener("click", () => {
        input.value = "-";
      });
      article.append(ignore);
      return article;
    }
  </script>
</body>
</html>
"""

SIMILAR_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Parecidos entre voces</title>
  <style>
    :root {
      color: #1c1915; background: #f4f0e6;
      font-family: "Segoe UI", "Liberation Sans", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; }
    main { max-width: 880px; margin: 0 auto; padding: 24px 20px 64px; }
    h1 { font-size: 1.4rem; margin: 0 0 8px; }
    h2 { font-size: 1.05rem; margin: 28px 0 8px; }
    p, li { color: #5c564c; }
    a { color: #1c1915; }
    article {
      background: #fffdf8; border: 1px solid #d5cdbc; border-radius: 10px;
      padding: 14px 16px; margin: 0 0 12px;
    }
    article h3 { font-size: 1rem; margin: 0 0 8px; }
    .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    audio { width: 100%; margin: 8px 0; }
    .bar { height: 8px; background: #e7e1d4; border-radius: 4px; margin: 6px 0 10px; }
    .bar span { display: block; height: 100%; background: #1c1915; border-radius: 4px; }
    .unite { display: flex; gap: 8px; margin-top: 8px; }
    .unite input {
      flex: 1; font: inherit; padding: 8px;
      border: 1px solid #d5cdbc; border-radius: 8px;
    }
    .unite button {
      font: inherit; padding: 8px 12px; border-radius: 8px;
      border: 1px solid #1c1915; background: #1c1915; color: #f4f0e6; cursor: pointer;
    }
    @media (max-width: 700px) { .pair { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <h1>Parecidos entre voces</h1>
    <p><a href="/">Poner nombres</a></p>
    <p id="note"></p>
    <h2>Entre grabaciones</h2>
    <div id="pairs"></div>
    <h2>Contra los perfiles guardados</h2>
    <div id="profiles"></div>
  </main>
  <script>
    const note = document.querySelector("#note");
    const pairs = document.querySelector("#pairs");
    const profiles = document.querySelector("#profiles");
    fetch("/api/similar").then((response) => response.json()).then((payload) => {
      const cut = Math.round(payload.threshold * 100);
      note.textContent = "A partir de " + cut
        + "% se considera la misma voz. Si dos grupos son la misma persona, unilos.";
      if (!payload.pairs.length) {
        pairs.textContent = "No hay pares para comparar.";
      }
      for (const pair of payload.pairs) {
        pairs.append(pairCard(pair));
      }
      for (const voice of payload.voices) {
        profiles.append(profileCard(voice));
      }
    }).catch(() => {
      note.textContent = "No se pudieron cargar los parecidos.";
    });

    function pairCard(pair) {
      const article = document.createElement("article");
      const title = document.createElement("h3");
      const left = heading(pair.left);
      const right = heading(pair.right);
      title.textContent = percent(pair.score) + " · " + left + " y " + right;
      article.append(title);
      article.append(bar(pair.score));
      const columns = document.createElement("div");
      columns.className = "pair";
      columns.append(side(pair.left), side(pair.right));
      article.append(columns);
      article.append(uniteRow(pair));
      return article;
    }

    function uniteRow(pair) {
      const row = document.createElement("div");
      row.className = "unite";
      const input = document.createElement("input");
      input.type = "text";
      input.value = suggestedName(pair);
      input.placeholder = "Nombre de la voz";
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Unir";
      const status = document.createElement("p");
      button.addEventListener("click", () => unite(pair, input, button, status));
      row.append(input, button);
      const wrap = document.createElement("div");
      wrap.append(row, status);
      return wrap;
    }

    function suggestedName(pair) {
      const left = cleanLabel(pair.left.label);
      const right = cleanLabel(pair.right.label);
      return left || right;
    }

    function cleanLabel(label) {
      if (!label || label === "sin nombre") return "";
      return label;
    }

    function unite(pair, input, button, status) {
      const name = input.value.trim();
      if (!name) {
        status.textContent = "Escribí el nombre de la voz.";
        return;
      }
      button.disabled = true;
      status.textContent = "Uniendo...";
      fetch("/api/voices/merge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ left: pair.left.id, right: pair.right.id, name: name }),
      }).then((response) => response.json().then((payload) => {
        if (!response.ok) {
          button.disabled = false;
          status.textContent = payload.message || "No se pudo unir.";
          return;
        }
        window.location.reload();
      })).catch(() => {
        button.disabled = false;
        status.textContent = "No se pudo unir.";
      });
    }

    function profileCard(voice) {
      const article = document.createElement("article");
      const title = document.createElement("h3");
      title.textContent = heading(voice);
      article.append(title);
      article.append(player(voice));
      if (!voice.profiles.length) {
        const empty = document.createElement("p");
        empty.textContent = "No se parece a un perfil guardado.";
        article.append(empty);
        return article;
      }
      const list = document.createElement("ul");
      for (const match of voice.profiles) {
        const item = document.createElement("li");
        item.textContent = match.name + " · " + percent(match.score);
        list.append(item);
      }
      article.append(list);
      return article;
    }

    function side(voice) {
      const block = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = heading(voice);
      block.append(title);
      const where = document.createElement("p");
      where.textContent = voice.sources || "";
      block.append(where);
      block.append(player(voice));
      return block;
    }

    function player(voice) {
      if (!voice.clip) {
        const missing = document.createElement("p");
        missing.textContent = "Sin clip.";
        return missing;
      }
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.preload = "none";
      audio.src = voice.clip;
      return audio;
    }

    function bar(score) {
      const track = document.createElement("div");
      track.className = "bar";
      const fill = document.createElement("span");
      fill.style.width = Math.max(0, Math.min(100, Math.round(score * 100))) + "%";
      track.append(fill);
      return track;
    }

    function heading(voice) {
      return voice.id + " · " + (voice.label || "sin nombre");
    }

    function percent(score) {
      return Math.round(score * 100) + "%";
    }
  </script>
</body>
</html>
"""


def serve_voice_wizard(clusters: list[VoiceCluster], *, open_browser: bool = True) -> int:
    if not clusters:
        print("No hay voces para mostrar.", flush=True)
        return 0
    httpd = bind_wizard(clusters)
    port = int(httpd.server_address[1])
    home = f"http://127.0.0.1:{port}/"
    similar = f"http://127.0.0.1:{port}/parecidos"
    pending = pending_voices(clusters, load_voice_bank())
    if pending:
        print(home, flush=True)
        print(f"Parecidos: {similar}", flush=True)
        open_url = home
    else:
        print("No hay voces nuevas.", flush=True)
        print(similar, flush=True)
        open_url = similar
    print("Ctrl+C cierra la página.", flush=True)
    if open_browser:
        threading.Thread(target=webbrowser.open, args=(open_url,), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()
    return 0


def pending_voices(clusters: list[VoiceCluster], bank) -> list[VoiceCluster]:
    return [cluster for cluster in clusters if is_new_voice(cluster, bank)]


WEAK_MATCH = 0.85


def namable_voices(clusters: list[VoiceCluster], bank) -> list[dict]:
    """Voces para poner nombre: nuevas, sin perfil, o con match flojo."""
    rows: list[dict] = []
    for cluster in clusters:
        scores = profile_match_scores(cluster, bank)
        best_name = scores[0][0] if scores else None
        best_score = scores[0][1] if scores else 0.0
        label = cluster_display_name(cluster, bank)
        if is_new_voice(cluster, bank):
            reason = "new"
        elif label is None:
            reason = "unnamed"
        elif best_score < WEAK_MATCH:
            reason = "weak"
        else:
            continue
        row = _voice_row(cluster)
        row["reason"] = reason
        row["label"] = label or "sin nombre"
        row["best_profile"] = best_name
        row["best_score"] = round(best_score, 3) if best_score else 0.0
        rows.append(row)
    rows.sort(key=lambda item: ({"new": 0, "unnamed": 1, "weak": 2}[item["reason"]], -item["id"]))
    return rows


def similar_payload(clusters: list[VoiceCluster]) -> dict:
    bank = load_voice_bank()
    rows = {cluster.cluster_id: _voice_row(cluster) for cluster in clusters}
    for cluster in clusters:
        label = cluster_display_name(cluster, bank)
        rows[cluster.cluster_id]["label"] = label or "sin nombre"
    pairs = []
    # Umbral un poco bajo el match oficial: sirven para revisar falsos negativos.
    floor = max(0.45, MATCH_SIMILARITY - 0.25)
    for left_id, right_id, score in voice_pair_scores(clusters):
        if score < floor:
            break
        pairs.append(
            {
                "left": rows[left_id],
                "right": rows[right_id],
                "score": round(score, 3),
            }
        )
        if len(pairs) >= 40:
            break
    voices = []
    for cluster in clusters:
        matches = [
            {"name": name, "score": round(score, 3)}
            for name, score in profile_match_scores(cluster, bank)[:3]
            if score > 0
        ]
        row = dict(rows[cluster.cluster_id])
        row["profiles"] = matches
        voices.append(row)
    voices.sort(
        key=lambda item: item["profiles"][0]["score"] if item["profiles"] else 0,
        reverse=True,
    )
    return {"threshold": MATCH_SIMILARITY, "pairs": pairs, "voices": voices}


def voice_payload(clusters: list[VoiceCluster]) -> dict:
    bank = load_voice_bank()
    namable = namable_voices(clusters, bank)
    return {
        "known_names": [profile.name for profile in bank.profiles],
        "voices": namable,
        "new_count": sum(1 for row in namable if row["reason"] == "new"),
        "threshold": MATCH_SIMILARITY,
        "weak_threshold": WEAK_MATCH,
    }


def save_submitted_names(clusters: list[VoiceCluster], raw_names: dict) -> dict:
    bank = load_voice_bank()
    allowed = {row["id"] for row in namable_voices(clusters, bank)}
    names: dict[int, str] = {}
    for key, value in raw_names.items():
        if not str(key).isdigit():
            continue
        cluster_id = int(key)
        if cluster_id not in allowed:
            continue
        cleaned = " ".join(str(value).strip().split())
        if "[" in cleaned or "]" in cleaned or not cleaned:
            continue
        names[cluster_id] = cleaned
    if not names:
        return {"ok": True, "message": "No había nombres para guardar."}
    selected = [cluster for cluster in clusters if cluster.cluster_id in names]
    vectors = [track.embedding for cluster in selected for track in cluster.tracks]
    current = without_embeddings(bank, vectors)
    added = bank_from_names(selected, names, threshold=current.threshold)
    save_voice_bank(merge_voice_banks(current, added))
    patch_names_file(names)
    saved = ", ".join(profile.name for profile in added.profiles)
    ignored = len(added.rejected)
    parts = []
    if saved:
        parts.append(f"Guardadas: {saved}.")
    if ignored:
        parts.append(f"Ignoradas: {ignored}.")
    parts.append("Las próximas transcripciones usan estos nombres.")
    return {"ok": True, "message": " ".join(parts)}


def merge_voice_pair(
    clusters: list[VoiceCluster],
    left_id: int,
    right_id: int,
    name: str,
) -> dict:
    cleaned = " ".join(name.strip().split())
    if not cleaned or cleaned == "-" or "[" in cleaned or "]" in cleaned:
        raise ValueError("Escribí el nombre de la voz.")
    if left_id == right_id:
        raise ValueError("Elegí dos voces distintas.")
    by_id = {cluster.cluster_id: cluster for cluster in clusters}
    left = by_id.get(left_id)
    right = by_id.get(right_id)
    if left is None or right is None:
        raise ValueError("Esa voz ya no está en la lista.")
    clip = left.clip_path or right.clip_path
    united = VoiceCluster(left.cluster_id, left.tracks + right.tracks, clip)
    updated = [
        united if cluster.cluster_id == left.cluster_id else cluster
        for cluster in clusters
        if cluster.cluster_id != right.cluster_id
    ]
    vectors = [track.embedding for track in united.tracks]
    current = without_embeddings(load_voice_bank(), vectors)
    added = bank_from_names([united], {united.cluster_id: cleaned}, threshold=current.threshold)
    save_voice_bank(merge_voice_banks(current, added))
    patch_names_file({left_id: cleaned, right_id: cleaned})
    save_review(updated)
    clusters[:] = updated
    return {"ok": True, "message": f"Quedó una sola voz: {cleaned}."}


def bind_wizard(clusters: list[VoiceCluster]) -> ThreadingHTTPServer:
    handler = _handler(clusters)
    last_error: OSError | None = None
    for port in range(WIZARD_PORT, WIZARD_PORT + PORT_SPAN):
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError as error:
            last_error = error
            continue
    raise RuntimeError(f"No pude abrir el asistente de voces ({last_error})")


def _handler(clusters: list[VoiceCluster]) -> type[BaseHTTPRequestHandler]:
    lock = threading.Lock()

    class WizardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                self._bytes(PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/voices":
                self._bytes(
                    json.dumps(voice_payload(clusters)).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
                return
            if path == "/parecidos":
                self._bytes(SIMILAR_PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/similar":
                with lock:
                    payload = similar_payload(clusters)
                self._bytes(
                    json.dumps(payload).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
                return
            if path.startswith("/clips/"):
                clip = clip_for(clusters, path.removeprefix("/clips/"))
                if clip is None:
                    self.send_error(404)
                    return
                self._bytes(clip.read_bytes(), "audio/wav")
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in {"/api/voices", "/api/voices/merge"}:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > MAX_BODY_BYTES:
                self.send_error(400)
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("El pedido no es válido.")
                if path == "/api/voices/merge":
                    try:
                        left_id = int(payload["left"])
                        right_id = int(payload["right"])
                    except (KeyError, TypeError, ValueError):
                        raise ValueError("Esa voz ya no está en la lista.") from None
                    with lock:
                        result = merge_voice_pair(
                            clusters,
                            left_id,
                            right_id,
                            str(payload.get("name") or ""),
                        )
                else:
                    raw_names = payload.get("names")
                    if not isinstance(raw_names, dict):
                        raise ValueError("falta names")
                    result = save_submitted_names(clusters, raw_names)
            except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
                message = str(error) if str(error) else "No se pudo guardar."
                body = json.dumps({"ok": False, "message": message}).encode("utf-8")
                self._bytes(body, "application/json; charset=utf-8", status=400)
                return
            self._bytes(json.dumps(result).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return WizardHandler


def _voice_row(cluster: VoiceCluster) -> dict:
    speech = sum(track.speech_seconds for track in cluster.tracks)
    sources = sorted({track.source_name for track in cluster.tracks})
    shown = ", ".join(sources[:3])
    if len(sources) > 3:
        shown = f"{shown} y {len(sources) - 3} más"
    clip = None
    if clip_for([cluster], f"{cluster.cluster_id}.wav") is not None:
        clip = f"/clips/{cluster.cluster_id}.wav"
    return {
        "id": cluster.cluster_id,
        "title": f"{cluster.cluster_id}  {format_duration(speech)}",
        "sources": shown,
        "clip": clip,
    }


def clip_for(clusters: list[VoiceCluster], name: str) -> Path | None:
    if "/" in name or "\\" in name or not name.endswith(".wav"):
        return None
    stem = name[:-4]
    if not stem.isdigit():
        return None
    cluster_id = int(stem)
    root = (voices_dir() / "clips").resolve()
    for cluster in clusters:
        if cluster.cluster_id != cluster_id or not cluster.clip_path:
            continue
        path = Path(cluster.clip_path).resolve()
        if path.parent != root or not path.is_file():
            return None
        return path
    return None
