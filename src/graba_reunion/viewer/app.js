const meetingsNode = document.querySelector("#meetings");
const titleNode = document.querySelector("#title");
const whenNode = document.querySelector("#when");
const audioPlayer = document.querySelector("#player");
const videoPlayer = document.querySelector("#video-player");
let player = audioPlayer;
const conversationNode = document.querySelector("#conversation");
const textNode = document.querySelector("#text");
const minutesView = document.querySelector("#minutes-view");
const minutesEdit = document.querySelector("#minutes-edit");
const speakerForm = document.querySelector("#speaker-form");
const tabButtons = Array.from(document.querySelectorAll(".tabs:not(.voices-subtabs) button"));
const hubButtons = Array.from(document.querySelectorAll("[data-hub]"));

let currentId = "";
let currentText = "";
let activeIndex = -1;
let currentHub = "conversations";

hubButtons.forEach((button) => {
  button.addEventListener("click", () => showHub(button.dataset.hub, true));
});

tabButtons.forEach((button) => {
  button.addEventListener("click", () => showTab(button.dataset.tab));
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => sendPrompt(button.dataset.prompt));
});

document.querySelector('[data-copy="transcript"]').addEventListener("click", copyTranscript);

document.querySelector("#btn-download-txt").addEventListener("click", () => {
  if (currentId) {
    window.location.href = "/api/meetings/" + encodeURIComponent(currentId) + "/files/txt";
  }
});

document.querySelector("#btn-download-md").addEventListener("click", () => {
  if (currentId) {
    window.location.href = "/api/meetings/" + encodeURIComponent(currentId) + "/files/minutes";
  }
});

document.querySelector("#btn-phrases").addEventListener("click", regeneratePhrases);
document.querySelector("#btn-groq").addEventListener("click", generateGroq);
document.querySelector("#btn-save-minutes").addEventListener("click", saveMinutes);
document.querySelector("#btn-save-speakers").addEventListener("click", saveSpeakers);

document.querySelector("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

document.querySelector("#transcribe-form").addEventListener("submit", (event) => {
  event.preventDefault();
  runTranscribe();
});

document.querySelectorAll("[data-voices-tab]").forEach((button) => {
  button.addEventListener("click", () => showVoicesTab(button.dataset.voicesTab));
});

function onTime(event) {
  if (event.currentTarget !== player) {
    return;
  }
  markPhrase(phraseIndexAt(player.currentTime));
}

audioPlayer.addEventListener("timeupdate", onTime);
videoPlayer.addEventListener("timeupdate", onTime);

window.addEventListener("popstate", () => {
  applyUrl(false);
});

applyUrl();

function applyUrl() {
  const params = new URLSearchParams(window.location.search);
  const tab = params.get("tab") || "conversations";
  showHub(tab, false, false);
  if (tab === "conversations") {
    loadMeetings(params.get("id") || "", numberOrNull(params.get("t")));
    return;
  }
  if (tab === "voices") {
    loadVoices();
  }
}

async function showHub(name, push, loadSide = true) {
  currentHub = name;
  hubButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.hub === name);
  });
  ["conversations", "search", "voices", "transcribe"].forEach((key) => {
    document.querySelector("#panel-" + key).hidden = key !== name;
  });
  if (push) {
    const url = new URL(window.location.href);
    if (name === "conversations") {
      url.searchParams.delete("tab");
    } else {
      url.searchParams.set("tab", name);
      url.searchParams.delete("id");
      url.searchParams.delete("t");
    }
    history.pushState({}, "", url);
  }
  if (!loadSide) {
    return;
  }
  if (name === "voices") {
    loadVoices();
  }
  if (name === "conversations" && !meetingsNode.children.length) {
    loadMeetings("", null);
  }
}

async function loadMeetings(requestedId, start) {
  const response = await fetch("/api/meetings");
  const meetings = await response.json();
  meetingsNode.replaceChildren();
  if (!meetings.length) {
    const item = document.createElement("li");
    item.className = "note";
    item.textContent = "No hay reuniones.";
    meetingsNode.append(item);
    return;
  }
  for (const meeting of meetings) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.id = meeting.id;
    const name = document.createElement("strong");
    name.textContent = meeting.title || meeting.id;
    const when = document.createElement("span");
    when.textContent = meeting.recorded_at || "";
    button.append(name, when);
    button.addEventListener("click", () => {
      const url = new URL(window.location.href);
      url.searchParams.delete("tab");
      url.searchParams.set("id", meeting.id);
      url.searchParams.delete("t");
      history.pushState({}, "", url);
      showHub("conversations", false, false);
      openMeeting(meeting.id, null, false);
    });
    item.append(button);
    meetingsNode.append(item);
  }
  const known = meetings.some((meeting) => meeting.id === requestedId);
  openMeeting(known ? requestedId : meetings[0].id, known ? start : null, false);
}

async function openMeeting(id, start, push) {
  if (!id) {
    return;
  }
  if (push) {
    const url = new URL(window.location.href);
    url.searchParams.delete("tab");
    url.searchParams.set("id", id);
    if (start == null) {
      url.searchParams.delete("t");
    } else {
      url.searchParams.set("t", String(start));
    }
    history.pushState({}, "", url);
  }
  const response = await fetch("/api/meetings/" + encodeURIComponent(id));
  if (!response.ok) {
    titleNode.textContent = "No está esa reunión";
    return;
  }
  const meeting = await response.json();
  currentId = meeting.id;
  currentText = meeting.text || "";
  activeIndex = -1;
  setMeetingControls(true, Boolean(meeting.has_minutes), Boolean(meeting.has_audio));
  document.querySelector("#prompt-status").hidden = true;
  document.querySelector("#prompt-fallback").hidden = true;
  titleNode.textContent = meeting.title || meeting.id;
  whenNode.textContent = meeting.recorded_at || "";
  document.querySelectorAll("#meetings button").forEach((button) => {
    button.classList.toggle("active", button.dataset.id === meeting.id);
  });
  textNode.textContent = meeting.text || "";
  minutesView.innerHTML = meeting.has_minutes ? renderMinutes(meeting.minutes || "") : "";
  minutesEdit.value = meeting.minutes || "";
  renderSpeakers(meeting.speakers || []);
  renderConversation(meeting);
  const initial = meeting.has_phrases ? "conversation" : "text";
  showTab(initial);
  if (meeting.has_audio && meeting.audio) {
    player = meeting.media_kind === "video" ? videoPlayer : audioPlayer;
    const other = player === audioPlayer ? videoPlayer : audioPlayer;
    other.pause();
    other.removeAttribute("src");
    other.hidden = true;
    player.hidden = false;
    const same = player.getAttribute("src") === meeting.audio;
    if (!same) {
      player.src = meeting.audio;
    }
    if (start != null) {
      const seek = () => {
        player.currentTime = start;
        player.play().catch(() => {});
        markPhrase(phraseIndexAt(start));
      };
      if (player.readyState >= 1 && same) {
        seek();
      } else {
        player.addEventListener("loadedmetadata", seek, { once: true });
      }
    }
  } else {
    audioPlayer.pause();
    videoPlayer.pause();
    audioPlayer.removeAttribute("src");
    videoPlayer.removeAttribute("src");
    audioPlayer.hidden = true;
    videoPlayer.hidden = true;
  }
}

function setMeetingControls(enabled, hasMinutes, hasAudio) {
  document.querySelectorAll("[data-prompt], [data-copy]").forEach((button) => {
    button.disabled = !enabled;
  });
  document.querySelector("#btn-download-txt").disabled = !enabled;
  document.querySelector("#btn-download-md").disabled = !enabled || !hasMinutes;
  document.querySelector("#btn-phrases").disabled = !enabled || !hasAudio;
  document.querySelector("#btn-groq").disabled = !enabled;
  document.querySelector("#btn-save-minutes").disabled = !enabled;
  document.querySelector("#btn-save-speakers").disabled = !enabled;
}

function renderSpeakers(speakers) {
  speakerForm.replaceChildren();
  if (!speakers.length) {
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = "No hay etiquetas SPEAKER_XX en esta reunión.";
    speakerForm.append(note);
    return;
  }
  for (const label of speakers) {
    const row = document.createElement("div");
    row.className = "speaker-row";
    const code = document.createElement("code");
    code.textContent = label;
    const input = document.createElement("input");
    input.type = "text";
    input.dataset.speaker = label;
    input.placeholder = "Nombre";
    row.append(code, input);
    speakerForm.append(row);
  }
}

function renderConversation(meeting) {
  conversationNode.replaceChildren();
  const phrases = meeting.phrases && Array.isArray(meeting.phrases.phrases)
    ? meeting.phrases.phrases
    : [];
  if (!meeting.has_phrases || !phrases.length) {
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = meeting.has_phrases
      ? "Esta transcripción no tiene frases con tiempo."
      : "Esta reunión no tiene el tiempo de cada frase. Podés leer el texto.";
    conversationNode.append(note);
    return;
  }
  let block = null;
  let blockSpeaker = null;
  for (const phrase of phrases) {
    if (block === null || phrase.speaker !== blockSpeaker) {
      block = document.createElement("article");
      block.className = "turn";
      const heading = document.createElement("h3");
      heading.textContent = phrase.speaker || "Sin nombre";
      block.append(heading);
      conversationNode.append(block);
      blockSpeaker = phrase.speaker;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "phrase";
    button.dataset.index = String(phrase.index);
    button.dataset.start = phrase.start == null ? "" : String(phrase.start);
    button.dataset.end = phrase.end == null ? "" : String(phrase.end);
    const time = document.createElement("time");
    time.textContent = phrase.clock || "";
    button.append(time, document.createTextNode(phrase.text || ""));
    button.addEventListener("click", () => {
      if (phrase.start == null) {
        return;
      }
      player.hidden = false;
      const seek = () => {
        player.currentTime = phrase.start;
        player.play().catch(() => {});
        markPhrase(phrase.index);
      };
      if (player.readyState >= 1) {
        seek();
      } else {
        player.addEventListener("loadedmetadata", seek, { once: true });
      }
    });
    block.append(button);
  }
}

async function copyTranscript() {
  if (!currentId) {
    return;
  }
  const status = document.querySelector("#prompt-status");
  const fallback = document.querySelector("#prompt-fallback");
  fallback.hidden = true;
  status.hidden = false;
  const text = currentText;
  if (!text) {
    status.textContent = "No hay texto para copiar.";
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = "Charla copiada.";
  } catch (error) {
    status.textContent = "No se pudo copiar. Seleccioná el texto.";
    fallback.hidden = false;
    fallback.value = text;
    fallback.focus();
    fallback.select();
  }
}

async function sendPrompt(kind) {
  if (!currentId) {
    return;
  }
  const status = document.querySelector("#prompt-status");
  const fallback = document.querySelector("#prompt-fallback");
  fallback.hidden = true;
  status.hidden = false;
  status.textContent = "Armando el texto...";
  const response = await fetch(
    "/api/meetings/" + encodeURIComponent(currentId) + "/prompts/" + kind,
  );
  if (!response.ok) {
    status.textContent = "No se pudo armar el texto.";
    return;
  }
  const prompt = await response.text();
  try {
    await navigator.clipboard.writeText(prompt);
    status.textContent = "Copiado. Pegalo en ChatGPT.";
    window.open("https://chatgpt.com/", "_blank");
  } catch (error) {
    status.textContent = "No se pudo copiar. Seleccioná el texto y abrí ChatGPT.";
    fallback.hidden = false;
    fallback.value = prompt;
    fallback.focus();
    fallback.select();
  }
}

async function saveMinutes() {
  if (!currentId) {
    return;
  }
  const status = document.querySelector("#prompt-status");
  status.hidden = false;
  status.textContent = "Guardando minuta...";
  const response = await fetch(
    "/api/meetings/" + encodeURIComponent(currentId) + "/minutes",
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: minutesEdit.value }),
    },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) {
    status.textContent = payload.message || "No se pudo guardar la minuta.";
    return;
  }
  status.textContent = payload.message || "Minuta guardada.";
  minutesView.innerHTML = renderMinutes(minutesEdit.value);
  document.querySelector("#btn-download-md").disabled = false;
}

async function generateGroq() {
  if (!currentId) {
    return;
  }
  const status = document.querySelector("#prompt-status");
  status.hidden = false;
  status.textContent = "Generando con Groq...";
  document.querySelector("#btn-groq").disabled = true;
  const response = await fetch(
    "/api/meetings/" + encodeURIComponent(currentId) + "/minutes/groq",
    { method: "POST" },
  );
  const payload = await response.json().catch(() => ({}));
  document.querySelector("#btn-groq").disabled = false;
  if (!response.ok || !payload.ok) {
    status.textContent = payload.message || "No se pudo generar la minuta.";
    return;
  }
  minutesEdit.value = payload.minutes || "";
  minutesView.innerHTML = renderMinutes(payload.minutes || "");
  document.querySelector("#btn-download-md").disabled = false;
  status.textContent = payload.message || "Minuta generada.";
  showTab("minutes");
}

async function regeneratePhrases() {
  if (!currentId) {
    return;
  }
  const status = document.querySelector("#prompt-status");
  status.hidden = false;
  status.textContent = "Regenerando frases...";
  document.querySelector("#btn-phrases").disabled = true;
  const response = await fetch(
    "/api/meetings/" + encodeURIComponent(currentId) + "/phrases",
    { method: "POST" },
  );
  const payload = await response.json().catch(() => ({}));
  document.querySelector("#btn-phrases").disabled = false;
  if (!response.ok || !payload.ok) {
    status.textContent = payload.message || "No se pudieron regenerar las frases.";
    return;
  }
  status.textContent = payload.message || "Frases listas.";
  openMeeting(currentId, null, false);
}

async function saveSpeakers() {
  if (!currentId) {
    return;
  }
  const names = {};
  speakerForm.querySelectorAll("input[data-speaker]").forEach((input) => {
    if (input.value.trim()) {
      names[input.dataset.speaker] = input.value.trim();
    }
  });
  const status = document.querySelector("#prompt-status");
  status.hidden = false;
  status.textContent = "Guardando nombres...";
  const response = await fetch(
    "/api/meetings/" + encodeURIComponent(currentId) + "/speakers",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ names }),
    },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) {
    status.textContent = payload.message || "No se pudieron guardar los nombres.";
    return;
  }
  status.textContent = payload.message || "Nombres guardados.";
  openMeeting(currentId, null, false);
}

async function runSearch() {
  const q = document.querySelector("#search-q").value.trim();
  const word = document.querySelector("#search-word").checked;
  const participant = document.querySelector("#search-participant").value.trim();
  const status = document.querySelector("#search-status");
  const hitsNode = document.querySelector("#search-hits");
  hitsNode.replaceChildren();
  status.textContent = "Buscando...";
  const params = new URLSearchParams();
  if (q) {
    params.set("q", q);
  }
  if (word) {
    params.set("word", "1");
  }
  if (participant) {
    params.set("participant", participant);
  }
  const response = await fetch("/api/search?" + params.toString());
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    status.textContent = payload.message || "No se pudo buscar.";
    return;
  }
  const hits = payload.hits || [];
  if (!hits.length) {
    status.textContent = "Sin resultados.";
    return;
  }
  status.textContent = hits.length + " resultado(s).";
  for (const hit of hits) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    const title = document.createElement("strong");
    title.textContent = hit.path || hit.id;
    const meta = document.createElement("span");
    const bits = [];
    if (hit.spoken_at) {
      bits.push(hit.spoken_at);
    }
    if (hit.speaker) {
      bits.push(hit.speaker);
    }
    if (hit.score != null) {
      bits.push(String(hit.score));
    }
    meta.textContent = bits.join(" · ");
    const snippet = document.createElement("span");
    snippet.textContent = hit.snippet || "";
    button.append(title, meta, snippet);
    button.addEventListener("click", () => {
      showHub("conversations", true, false);
      const url = new URL(window.location.href);
      url.searchParams.delete("tab");
      url.searchParams.set("id", hit.id);
      if (hit.t != null) {
        url.searchParams.set("t", String(hit.t));
      } else {
        url.searchParams.delete("t");
      }
      history.pushState({}, "", url);
      loadMeetings(hit.id, hit.t == null ? null : Number(hit.t));
    });
    item.append(button);
    hitsNode.append(item);
  }
}

async function runTranscribe() {
  const input = document.querySelector("#transcribe-files");
  const joinBox = document.querySelector("#transcribe-join");
  const status = document.querySelector("#transcribe-status");
  if (!input.files || !input.files.length) {
    status.textContent = "Elegí al menos un archivo.";
    return;
  }
  const join = Boolean(joinBox && joinBox.checked && input.files.length > 1);
  status.textContent = join
    ? "Uniendo audios y transcribiendo... puede demorar."
    : "Transcribiendo... puede demorar.";
  const body = new FormData();
  for (const file of input.files) {
    body.append("files", file, file.name);
  }
  const url = "/api/transcribe" + (join ? "?join=1" : "");
  const response = await fetch(url, { method: "POST", body });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) {
    status.textContent = payload.message || "Falló la transcripción.";
    return;
  }
  const ids = payload.ids || [];
  status.textContent = payload.message || "Listo.";
  if (ids.length) {
    showHub("conversations", true, false);
    const next = new URL(window.location.href);
    next.searchParams.delete("tab");
    next.searchParams.set("id", ids[0]);
    history.pushState({}, "", next);
    loadMeetings(ids[0], null);
  }
}

async function loadVoices() {
  const status = document.querySelector("#voices-status");
  status.textContent = "Cargando voces...";
  const response = await fetch("/api/voices");
  const payload = await response.json().catch(() => ({}));
  if (!payload.ready) {
    status.textContent = payload.message || "No hay voces preparadas.";
    document.querySelector("#voices-new").replaceChildren();
    document.querySelector("#voices-similar").replaceChildren();
    document.querySelector("#voices-profiles").replaceChildren();
    return;
  }
  const count = (payload.voices || []).length;
  status.textContent = count
    ? count + " voz(ces) para nombrar o revisar. Escuchá el clip y escribí el nombre."
    : "No hay voces pendientes. En Parecidos podés unir grupos de la misma persona.";
  renderNewVoices(payload);
  loadSimilar();
  renderProfiles(payload.known_names || []);
}

function voiceReasonLabel(reason, voice) {
  if (reason === "new") {
    return "Nueva (sin perfil)";
  }
  if (reason === "unnamed") {
    return "Sin nombre asignado";
  }
  if (reason === "weak") {
    const score = Math.round((voice.best_score || 0) * 100);
    return "Match flojo con " + (voice.best_profile || "?") + " (" + score + "%)";
  }
  return "";
}

function renderNewVoices(payload) {
  const root = document.querySelector("#voices-new");
  root.replaceChildren();
  const help = document.createElement("p");
  help.className = "note";
  help.textContent =
    "Escuchá el clip. Escribí el nombre (podés reusar uno de la lista). "
    + "Un guion (-) la ignora (ruido/música). Vacío la deja para después. "
    + "Los nombres valen para las próximas transcripciones; no reescriben textos viejos.";
  root.append(help);
  const voices = payload.voices || [];
  if (!voices.length) {
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = "No hay voces para nombrar ahora.";
    root.append(note);
    return;
  }
  ensureKnownNamesList(payload.known_names || []);
  for (const voice of voices) {
    const card = document.createElement("div");
    card.className = "voice-card";
    const title = document.createElement("strong");
    title.textContent = voice.title || String(voice.id);
    const badge = document.createElement("span");
    badge.className = "voice-badge";
    badge.textContent = voiceReasonLabel(voice.reason, voice);
    const sources = document.createElement("p");
    sources.className = "note";
    sources.textContent = voice.sources || "";
    card.append(title, badge, sources);
    if (voice.clip) {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.preload = "none";
      audio.src = voice.clip;
      card.append(audio);
    } else {
      const missing = document.createElement("p");
      missing.className = "note";
      missing.textContent = "Sin clip de audio.";
      card.append(missing);
    }
    const input = document.createElement("input");
    input.type = "text";
    input.dataset.voiceId = String(voice.id);
    input.setAttribute("list", "known-names");
    input.placeholder = "Nombre (- para ignorar)";
    if (voice.reason === "weak" && voice.best_profile) {
      input.value = voice.best_profile;
    }
    const ignore = document.createElement("button");
    ignore.type = "button";
    ignore.textContent = "Ignorar";
    ignore.addEventListener("click", () => {
      input.value = "-";
    });
    const row = document.createElement("div");
    row.className = "voices-actions";
    row.append(input, ignore);
    card.append(row);
    root.append(card);
  }
  const actions = document.createElement("div");
  actions.className = "voices-actions";
  const save = document.createElement("button");
  save.type = "button";
  save.textContent = "Guardar nombres";
  save.addEventListener("click", saveVoiceNames);
  actions.append(save);
  root.append(actions);
}

function ensureKnownNamesList(names) {
  let datalist = document.querySelector("#known-names");
  if (!datalist) {
    datalist = document.createElement("datalist");
    datalist.id = "known-names";
    document.body.append(datalist);
  }
  datalist.replaceChildren();
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    datalist.append(option);
  }
}

async function saveVoiceNames() {
  const names = {};
  document.querySelectorAll("#voices-new input[data-voice-id]").forEach((input) => {
    if (input.value.trim()) {
      names[input.dataset.voiceId] = input.value.trim();
    }
  });
  const status = document.querySelector("#voices-status");
  status.textContent = "Guardando...";
  const response = await fetch("/api/voices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ names }),
  });
  const payload = await response.json().catch(() => ({}));
  status.textContent = payload.message || (response.ok ? "Listo." : "Error.");
  loadVoices();
}

async function loadSimilar() {
  const root = document.querySelector("#voices-similar");
  root.replaceChildren();
  const response = await fetch("/api/similar");
  const payload = await response.json().catch(() => ({}));
  if (!payload.ready) {
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = payload.message || "Sin datos.";
    root.append(note);
    return;
  }
  const cut = Math.round((payload.threshold || 0.7) * 100);
  const help = document.createElement("p");
  help.className = "note";
  help.textContent =
    "Cómo usar: escuchá los dos clips. Si es la misma persona, escribí el nombre "
    + "y tocá Unir (queda un solo perfil). Si no es la misma, no hagas nada con ese par. "
    + "A partir de " + cut + "% el sistema las trata como la misma voz.";
  root.append(help);

  const pairsTitle = document.createElement("h2");
  pairsTitle.textContent = "Pares parecidos (entre grabaciones)";
  root.append(pairsTitle);
  const pairs = payload.pairs || [];
  if (!pairs.length) {
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = "No hay pares lo bastante parecidos.";
    root.append(note);
  }
  for (const pair of pairs) {
    root.append(similarPairCard(pair));
  }

  const profilesTitle = document.createElement("h2");
  profilesTitle.textContent = "Cada voz vs perfiles guardados";
  root.append(profilesTitle);
  const voices = payload.voices || [];
  if (!voices.length) {
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = "Sin voces en el review.";
    root.append(note);
    return;
  }
  for (const voice of voices) {
    root.append(similarProfileCard(voice));
  }
}

function similarPairCard(pair) {
  const card = document.createElement("div");
  card.className = "voice-card";
  const title = document.createElement("strong");
  title.textContent =
    percent(pair.score) + " · " + voiceHeading(pair.left) + " y " + voiceHeading(pair.right);
  card.append(title);
  card.append(scoreBar(pair.score));
  const columns = document.createElement("div");
  columns.className = "similar-pair";
  columns.append(similarSide(pair.left), similarSide(pair.right));
  card.append(columns);
  const row = document.createElement("div");
  row.className = "voices-actions";
  const name = document.createElement("input");
  name.type = "text";
  name.placeholder = "Nombre de la persona";
  const leftLabel = cleanVoiceLabel(pair.left.label);
  const rightLabel = cleanVoiceLabel(pair.right.label);
  name.value = leftLabel || rightLabel;
  const merge = document.createElement("button");
  merge.type = "button";
  merge.textContent = "Unir en un perfil";
  const localStatus = document.createElement("p");
  localStatus.className = "note";
  merge.addEventListener("click", async () => {
    if (!name.value.trim()) {
      localStatus.textContent = "Escribí el nombre antes de unir.";
      return;
    }
    merge.disabled = true;
    localStatus.textContent = "Uniendo...";
    const result = await fetch("/api/voices/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        left: pair.left.id,
        right: pair.right.id,
        name: name.value.trim(),
      }),
    });
    const body = await result.json().catch(() => ({}));
    if (!result.ok || body.ok === false) {
      merge.disabled = false;
      localStatus.textContent = body.message || "No se pudo unir.";
      return;
    }
    document.querySelector("#voices-status").textContent =
      body.message || "Unidas.";
    loadVoices();
  });
  row.append(name, merge);
  card.append(row, localStatus);
  return card;
}

function similarProfileCard(voice) {
  const card = document.createElement("div");
  card.className = "voice-card";
  const title = document.createElement("strong");
  title.textContent = voiceHeading(voice);
  card.append(title);
  if (voice.clip) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "none";
    audio.src = voice.clip;
    card.append(audio);
  }
  const matches = voice.profiles || [];
  if (!matches.length) {
    const empty = document.createElement("p");
    empty.className = "note";
    empty.textContent = "No se parece a un perfil guardado.";
    card.append(empty);
    return card;
  }
  const list = document.createElement("ul");
  for (const match of matches) {
    const item = document.createElement("li");
    item.textContent = match.name + " · " + percent(match.score);
    list.append(item);
  }
  card.append(list);
  return card;
}

function similarSide(voice) {
  const block = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = voiceHeading(voice);
  const where = document.createElement("p");
  where.className = "note";
  where.textContent = voice.sources || "";
  block.append(title, where);
  if (voice.clip) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "none";
    audio.src = voice.clip;
    block.append(audio);
  } else {
    const missing = document.createElement("p");
    missing.className = "note";
    missing.textContent = "Sin clip.";
    block.append(missing);
  }
  return block;
}

function voiceHeading(voice) {
  return (voice.id || "") + " · " + (voice.label || "sin nombre");
}

function cleanVoiceLabel(label) {
  if (!label || label === "sin nombre") {
    return "";
  }
  return label;
}

function percent(score) {
  return Math.round((Number(score) || 0) * 100) + "%";
}

function scoreBar(score) {
  const track = document.createElement("div");
  track.className = "score-bar";
  const fill = document.createElement("span");
  fill.style.width = Math.max(0, Math.min(100, Math.round((Number(score) || 0) * 100))) + "%";
  track.append(fill);
  return track;
}

function renderProfiles(names) {
  const root = document.querySelector("#voices-profiles");
  root.replaceChildren();
  if (!names.length) {
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = "Todavía no hay perfiles guardados.";
    root.append(note);
    return;
  }
  const list = document.createElement("ul");
  for (const name of names) {
    const item = document.createElement("li");
    item.textContent = name;
    list.append(item);
  }
  root.append(list);
}

function showVoicesTab(name) {
  document.querySelectorAll("[data-voices-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.voicesTab === name);
  });
  document.querySelector("#voices-new").hidden = name !== "new";
  document.querySelector("#voices-similar").hidden = name !== "similar";
  document.querySelector("#voices-profiles").hidden = name !== "profiles";
}

function showTab(name) {
  const sections = {
    conversation: conversationNode,
    text: textNode,
    minutes: document.querySelector("#minutes"),
    speakers: document.querySelector("#speakers"),
  };
  for (const [key, section] of Object.entries(sections)) {
    section.hidden = key !== name;
  }
  tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
}

function phraseIndexAt(seconds) {
  const buttons = conversationNode.querySelectorAll(".phrase");
  for (const button of buttons) {
    const start = Number(button.dataset.start);
    const end = Number(button.dataset.end);
    if (Number.isNaN(start)) {
      continue;
    }
    const limit = Number.isNaN(end) ? start + 0.001 : end;
    if (seconds >= start && seconds < limit) {
      return Number(button.dataset.index);
    }
  }
  return -1;
}

function markPhrase(index) {
  if (index === activeIndex) {
    return;
  }
  activeIndex = index;
  let target = null;
  conversationNode.querySelectorAll(".phrase").forEach((button) => {
    const active = Number(button.dataset.index) === index;
    button.classList.toggle("active", active);
    if (active) {
      target = button;
    }
  });
  if (target) {
    target.scrollIntoView({ block: "nearest" });
  }
}

function numberOrNull(value) {
  if (value == null || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function renderMinutes(source) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const parts = [];
  let list = null;
  let ordered = false;
  const flushList = () => {
    if (list) {
      parts.push((ordered ? "<ol>" : "<ul>") + list.join("") + (ordered ? "</ol>" : "</ul>"));
      list = null;
    }
  };
  for (const line of lines) {
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    const item = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(line);
    if (heading) {
      flushList();
      const level = heading[1].length;
      parts.push("<h" + level + ">" + inline(heading[2]) + "</h" + level + ">");
      continue;
    }
    if (item) {
      const isOrdered = /^\d+\./.test(item[2]);
      if (!list || ordered !== isOrdered) {
        flushList();
        list = [];
        ordered = isOrdered;
      }
      list.push("<li>" + inline(item[3]) + "</li>");
      continue;
    }
    flushList();
    if (line.trim()) {
      parts.push("<p>" + inline(line) + "</p>");
    }
  }
  flushList();
  return '<div class="minutes">' + parts.join("") + "</div>";
}

function inline(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
