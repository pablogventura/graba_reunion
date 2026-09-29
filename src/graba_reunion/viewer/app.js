const meetingsNode = document.querySelector("#meetings");
const titleNode = document.querySelector("#title");
const whenNode = document.querySelector("#when");
const player = document.querySelector("#player");
const conversationNode = document.querySelector("#conversation");
const textNode = document.querySelector("#text");
const minutesNode = document.querySelector("#minutes");
const tabButtons = Array.from(document.querySelectorAll(".tabs button"));

let currentId = "";
let activeIndex = -1;
let pendingStart = null;

tabButtons.forEach((button) => {
  button.addEventListener("click", () => showTab(button.dataset.tab));
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => sendPrompt(button.dataset.prompt));
});

player.addEventListener("timeupdate", () => {
  markPhrase(phraseIndexAt(player.currentTime));
});

window.addEventListener("popstate", () => {
  const params = new URLSearchParams(window.location.search);
  openMeeting(params.get("id") || "", numberOrNull(params.get("t")), false);
});

loadMeetings();

async function loadMeetings() {
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
      url.search = "";
      url.searchParams.set("id", meeting.id);
      history.pushState({}, "", url);
      openMeeting(meeting.id, null, false);
    });
    item.append(button);
    meetingsNode.append(item);
  }
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("id");
  const known = meetings.some((meeting) => meeting.id === requested);
  const start = known ? numberOrNull(params.get("t")) : null;
  openMeeting(known ? requested : meetings[0].id, start, false);
}

async function openMeeting(id, start, push) {
  if (!id) {
    return;
  }
  if (push) {
    const url = new URL(window.location.href);
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
  activeIndex = -1;
  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.disabled = false;
  });
  document.querySelector("#prompt-status").hidden = true;
  document.querySelector("#prompt-fallback").hidden = true;
  pendingStart = start;
  titleNode.textContent = meeting.title || meeting.id;
  whenNode.textContent = meeting.recorded_at || "";
  document.querySelectorAll("#meetings button").forEach((button) => {
    button.classList.toggle("active", button.dataset.id === meeting.id);
  });
  const minutesButton = document.querySelector('[data-tab="minutes"]');
  minutesButton.hidden = !meeting.has_minutes;
  textNode.textContent = meeting.text || "";
  minutesNode.innerHTML = meeting.has_minutes ? renderMinutes(meeting.minutes || "") : "";
  renderConversation(meeting);
  const initial = meeting.has_phrases ? "conversation" : "text";
  showTab(initial);
  if (meeting.has_audio && meeting.audio) {
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
    player.removeAttribute("src");
    player.hidden = true;
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

function showTab(name) {
  const sections = {
    conversation: conversationNode,
    text: textNode,
    minutes: minutesNode,
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
