/* Editor de Clips Virales — interfaz local sin build ni dependencias. */

const STORAGE_KEY = "viralclip.apiKey";
const MAX_FILE_BYTES = 2_000_000;

const state = {
  apiKey: sessionStorage.getItem(STORAGE_KEY) || "",
  activeId: null,
  config: null,
  flags: [],
  currentJob: null,
  eventSource: null,
  pollTimer: null,
  transcriptionId: null,
  transcription: null,
  transcriptionEventSource: null,
  transcriptionPollTimer: null,
  renderWatchers: [],
};

const $ = (id) => document.getElementById(id);

const healthBadge = $("health-badge");
const analysisForm = $("analysis-form");
const transcriptFile = $("transcript-file");
const transcriptText = $("transcript-text");
const platformSelect = $("platform");
const maxClipsInput = $("max-clips");
const minDurationInput = $("min-duration");
const maxDurationInput = $("max-duration");
const useLlmInput = $("use-llm");
const analyzeBtn = $("analyze-btn");
const sampleBtn = $("sample-btn");
const formStatus = $("form-status");
const historyList = $("history-list");
const historyStatus = $("history-status");
const refreshHistoryBtn = $("refresh-history");
const detail = $("detail");
const detailTitle = $("detail-title");
const detailMeta = $("detail-meta");
const detailError = $("detail-error");
const exportActions = $("export-actions");
const clipsList = $("clips");
const clipsEmpty = $("clips-empty");
const closeDetailBtn = $("close-detail");
const settingsDialog = $("settings-dialog");
const settingsForm = $("settings-form");
const apiKeyInput = $("api-key");
const clearSettingsBtn = $("clear-settings");
const openSettingsBtn = $("open-settings");
const flagsList = $("flags-list");
const flagsStatus = $("flags-status");
const toast = $("toast");
const clipTemplate = $("clip-template");
const transcribeForm = $("transcribe-form");
const videoFile = $("video-file");
const videoPath = $("video-path");
const videoDrop = $("video-drop");
const videoHelp = $("video-help");
const whisperModel = $("whisper-model");
const whisperLanguage = $("whisper-language");
const transcribeBtn = $("transcribe-btn");
const transcribeProgressWrap = $("transcribe-progress-wrap");
const transcribeProgress = $("transcribe-progress");
const transcribeStage = $("transcribe-stage");
const transcribeStatus = $("transcribe-status");
const transcribeResult = $("transcribe-result");
const transcribeMeta = $("transcribe-meta");
const analyzeTranscriptionBtn = $("analyze-transcription");
const loadTranscriptJsonBtn = $("load-transcript-json");
const copyTranscriptJsonBtn = $("copy-transcript-json");

const STATUS = {
  queued: { label: "En cola", variant: "neutral" },
  running: { label: "En proceso", variant: "warn" },
  done: { label: "Listo", variant: "ok" },
  error: { label: "Error", variant: "error" },
};

const PLATFORMS = {
  tiktok: "TikTok",
  reels: "Instagram Reels",
  shorts: "YouTube Shorts",
};

const FLAG_LABELS = {
  export_srt: "Exportar subtítulos SRT/VTT",
  sse_progress: "Progreso en tiempo real (SSE)",
};

const MODEL_LABELS = {
  tiny: "tiny (muy rápido)",
  base: "base (rápido)",
  small: "small (equilibrado)",
  medium: "medium (más preciso)",
  "large-v3": "large-v3 (máxima precisión)",
};

const SAMPLE_TRANSCRIPT = [
  { start: 0, end: 6, text: "Nadie te cuenta esto: el 80% de las ventas se pierde por no preguntar." },
  { start: 6, end: 12, text: "El error que frena tus ventas es hablar demasiado." },
  { start: 12, end: 18, text: "Tienes que dejar de hablar y empezar a escuchar." },
  { start: 18, end: 24, text: "La pregunta más poderosa es: ¿qué te impide comprar hoy?" },
  { start: 24, end: 30, text: "Cuando la haces, el cliente te dice exactamente qué necesita." },
  { start: 30, end: 36, text: "Y tú dejas de adivinar. Dejas de improvisar." },
  { start: 36, end: 42, text: "Es un error brutal que te cuesta miles de euros cada mes." },
  { start: 42, end: 48, text: "Prueba esta semana: haz una sola pregunta y calla." },
  { start: 48, end: 54, text: "Vas a ver cómo cambia la conversación." },
  { start: 54, end: 60, text: "Guarda este video antes de que lo borre." },
  { start: 60, end: 66, text: "Y sígueme para más estrategias de ventas sin humo." },
  { start: 66, end: 72, text: "Porque vender no es convencer: es entender." },
];

class ApiError extends Error {
  constructor(status, payload) {
    super((payload && payload.message) || `Error HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = payload && payload.code;
    this.detail = payload && payload.detail;
  }
}

/* ------------------------------------------------------------------ */
/* Cliente API                                                         */
/* ------------------------------------------------------------------ */

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.apiKey) {
    headers.set("X-API-Key", state.apiKey);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (error) {
    throw new ApiError(0, {
      message: "No se pudo conectar con el servidor local.",
      detail: error.message,
    });
  }

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("content-type") || "";
  let data = null;
  if (contentType.includes("application/json")) {
    data = await response.json().catch(() => null);
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const payload =
      data && typeof data === "object"
        ? data
        : { message: typeof data === "string" && data ? data : undefined };
    throw new ApiError(response.status, payload);
  }

  return data;
}

function describeError(error) {
  if (error instanceof ApiError) {
    if (error.code && error.detail) {
      return `${error.code}: ${error.message} (${error.detail})`;
    }
    if (error.code) {
      return `${error.code}: ${error.message}`;
    }
    return error.message;
  }
  return (error && error.message) || "Ocurrió un error inesperado.";
}

/* ------------------------------------------------------------------ */
/* Utilidades de interfaz                                              */
/* ------------------------------------------------------------------ */

function setBadge(text, variant, title = "") {
  healthBadge.textContent = text;
  healthBadge.className = `badge badge-${variant}`;
  healthBadge.title = title;
}

function setStatus(element, message, kind = "") {
  element.textContent = message;
  element.classList.remove("is-error", "is-success");
  if (kind) {
    element.classList.add(`is-${kind}`);
  }
}

let toastTimer = null;

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 2800);
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value || "—";
  }
  return new Intl.DateTimeFormat("es", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) {
    return "";
  }
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function platformLabel(value) {
  return PLATFORMS[value] || value || "—";
}

function statusBadge(status) {
  const info = STATUS[status] || { label: status, variant: "neutral" };
  const badge = document.createElement("span");
  badge.className = `badge badge-${info.variant}`;
  badge.textContent = info.label;
  return badge;
}

function metaItem(label, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "meta-item";
  const labelEl = document.createElement("span");
  labelEl.className = "meta-label";
  labelEl.textContent = label;
  const valueEl = document.createElement("span");
  valueEl.className = "meta-value";
  if (value instanceof Node) {
    valueEl.append(value);
  } else {
    valueEl.textContent = value;
  }
  wrapper.append(labelEl, valueEl);
  return wrapper;
}

async function copyText(text, label) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      fallbackCopy(text);
    }
    showToast(`${label} copiado.`);
  } catch {
    showToast("No se pudo copiar. Selecciona el texto manualmente.");
  }
}

function fallbackCopy(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

async function downloadFile(path, filename) {
  try {
    const headers = new Headers();
    if (state.apiKey) {
      headers.set("X-API-Key", state.apiKey);
    }
    const response = await fetch(path, { headers });
    if (!response.ok) {
      let payload = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      throw new ApiError(response.status, payload);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    showToast(describeError(error));
  }
}

/* ------------------------------------------------------------------ */
/* Salud y configuración                                               */
/* ------------------------------------------------------------------ */

async function loadHealth() {
  setBadge("Comprobando…", "neutral");
  try {
    const data = await api("/api/health");
    if (data.status === "ok") {
      setBadge("Sistema listo", "ok", "Base de datos y Ollama disponibles.");
    } else {
      const reasons = [];
      if (data.database !== "ok") {
        reasons.push("base de datos con problemas");
      }
      if (data.ollama && data.ollama.available === false) {
        reasons.push(data.ollama.message || "Ollama no disponible");
      }
      setBadge("Modo degradado", "warn", reasons.join(" · "));
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setBadge("API key inválida", "error", "Abre Ajustes y revisa la clave.");
    } else {
      setBadge("Sin conexión", "error", describeError(error));
    }
  }
}

async function loadConfig() {
  try {
    const config = await api("/api/config");
    state.config = config;
    state.flags = Array.isArray(config.flags) ? config.flags : [];
    applyFlags();
    if (Number.isFinite(config.max_clips)) {
      maxClipsInput.max = String(config.max_clips);
      if (Number(maxClipsInput.value) > config.max_clips) {
        maxClipsInput.value = String(config.max_clips);
      }
    }
    applyTranscriptionConfig(config);
  } catch {
    // La configuración es informativa; el formulario sigue usable.
  }
}

function applyTranscriptionConfig(config) {
  if (Array.isArray(config.whisper_models) && config.whisper_models.length) {
    const previous = whisperModel.value;
    whisperModel.replaceChildren();
    for (const model of config.whisper_models) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = MODEL_LABELS[model] || model;
      whisperModel.append(option);
    }
    whisperModel.value = config.whisper_models.includes(previous)
      ? previous
      : config.whisper_model || config.whisper_models[0];
  }

  if (
    config.whisper_language &&
    Array.from(whisperLanguage.options).some(
      (option) => option.value === config.whisper_language,
    )
  ) {
    whisperLanguage.value = config.whisper_language;
  }

  if (Number.isFinite(config.upload_max_bytes)) {
    const megabytes = Math.round(config.upload_max_bytes / 1_000_000);
    videoHelp.textContent =
      `Arrastra un archivo aquí o selecciónalo. MP4, MKV, MOV, WebM, MP3, WAV… ` +
      `hasta ${megabytes} MB.`;
  }

  if (config.ffmpeg_available === false) {
    transcribeBtn.disabled = true;
    setStatus(
      transcribeStatus,
      "FFmpeg no está disponible. Instálalo y comprueba «ffmpeg -version».",
      "error",
    );
  } else {
    transcribeBtn.disabled = false;
  }
}

function flagEnabled(name) {
  return state.flags.includes(name);
}

function applyFlags() {
  const srtEnabled = flagEnabled("export_srt");
  for (const link of exportActions.querySelectorAll(
    '[data-export="srt"], [data-export="vtt"]',
  )) {
    link.hidden = !srtEnabled;
  }
  for (const link of clipsList.querySelectorAll(".clip-srt")) {
    link.hidden = !srtEnabled;
  }
}

async function loadFlags() {
  setStatus(flagsStatus, "Cargando funciones…");
  try {
    const flags = await api("/api/flags");
    renderFlags(flags);
    setStatus(flagsStatus, "");
  } catch (error) {
    setStatus(flagsStatus, describeError(error), "error");
  }
}

function renderFlags(flags) {
  flagsList.replaceChildren();
  for (const flag of flags) {
    const item = document.createElement("div");
    item.className = "flag-item";

    const label = document.createElement("label");
    label.className = "flag-check";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(flag.enabled);
    input.addEventListener("change", () =>
      updateFlag(flag.name, input.checked),
    );
    const name = document.createElement("span");
    name.className = "flag-name";
    name.textContent = FLAG_LABELS[flag.name] || flag.name;
    label.append(input, name);

    const description = document.createElement("p");
    description.className = "flag-description";
    description.textContent = flag.description || "";

    item.append(label, description);
    flagsList.append(item);
  }
}

async function updateFlag(name, enabled) {
  setStatus(flagsStatus, "Guardando…");
  try {
    await api("/api/flags", {
      method: "PATCH",
      body: JSON.stringify({ name, enabled }),
    });
    await loadConfig();
    await loadFlags();
    setStatus(flagsStatus, "Función actualizada.", "success");
    showToast("Función actualizada.");
  } catch (error) {
    setStatus(flagsStatus, describeError(error), "error");
    await loadFlags();
  }
}

/* ------------------------------------------------------------------ */
/* Historial                                                           */
/* ------------------------------------------------------------------ */

async function loadHistory() {
  setStatus(historyStatus, "Cargando historial…");
  try {
    const data = await api("/api/analyses?limit=20");
    renderHistory(data.items || []);
    if (!data.total) {
      setStatus(historyStatus, "Aún no hay análisis.");
    } else {
      setStatus(
        historyStatus,
        `${data.total} análisis en total. Mostrando ${data.items.length}.`,
      );
    }
  } catch (error) {
    setStatus(historyStatus, describeError(error), "error");
  }
}

function renderHistory(items) {
  historyList.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "history-empty";
    empty.textContent = "Todavía no analizaste ninguna transcripción.";
    historyList.append(empty);
    return;
  }
  for (const job of items) {
    historyList.append(renderHistoryItem(job));
  }
}

function renderHistoryItem(job) {
  const item = document.createElement("li");
  item.className = "history-item";
  item.dataset.id = job.id;
  if (job.id === state.activeId) {
    item.classList.add("is-active");
  }

  const top = document.createElement("div");
  top.className = "history-top";
  const title = document.createElement("span");
  title.className = "history-title";
  title.textContent = `${platformLabel(job.platform)} · ${formatDate(job.created_at)}`;
  top.append(title, statusBadge(job.status));

  const meta = document.createElement("p");
  meta.className = "history-meta";
  const engine = job.engine
    ? `${job.engine.name}${job.engine.degraded ? " · degradado" : ""}`
    : "Sin motor aún";
  meta.textContent = `${String(job.id).slice(0, 8)}… · ${engine}`;

  const actions = document.createElement("div");
  actions.className = "history-actions";
  const open = document.createElement("button");
  open.type = "button";
  open.className = "btn btn-small btn-ghost";
  open.textContent = "Abrir";
  open.addEventListener("click", () => openDetail(job.id));
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "btn btn-small btn-ghost";
  remove.textContent = "Borrar";
  remove.addEventListener("click", () => deleteAnalysis(job.id));
  actions.append(open, remove);

  item.append(top, meta, actions);
  return item;
}

function markActiveHistory() {
  for (const item of historyList.querySelectorAll(".history-item")) {
    item.classList.toggle("is-active", item.dataset.id === state.activeId);
  }
}

/* ------------------------------------------------------------------ */
/* Detalle y clips                                                     */
/* ------------------------------------------------------------------ */

async function openDetail(id, { focus = true } = {}) {
  state.activeId = id;
  stopWatching();
  stopRenderWatchers();
  detail.hidden = false;
  detailTitle.textContent = "Resultado";
  detailMeta.replaceChildren();
  detailError.hidden = true;
  detailError.textContent = "";
  exportActions.hidden = true;
  clipsList.replaceChildren();
  clipsEmpty.hidden = true;

  try {
    const job = await api(`/api/analyses/${encodeURIComponent(id)}`);
    renderDetail(job);
    markActiveHistory();
    if (job.status === "queued" || job.status === "running") {
      watchAnalysis(id);
    }
    if (focus) {
      detailTitle.focus();
    }
  } catch (error) {
    detailError.hidden = false;
    detailError.textContent = describeError(error);
  }
}

function renderDetail(job) {
  state.currentJob = job;
  detailTitle.textContent = `Resultado · ${platformLabel(job.platform)}`;
  const progressLabel = `${job.progress ?? 0}%${
    job.stage ? ` · ${job.stage}` : ""
  }`;
  detailMeta.replaceChildren(
    metaItem("Estado", statusBadge(job.status)),
    metaItem("Progreso", progressLabel),
    metaItem("Motor", job.engine ? job.engine.name : "—"),
    metaItem(
      "Degradado",
      job.engine ? (job.engine.degraded ? "Sí" : "No") : "—",
    ),
    metaItem("Creado", formatDate(job.created_at)),
  );

  if (job.engine && job.engine.notes) {
    detailMeta.append(metaItem("Nota del motor", job.engine.notes));
  }

  if (job.error) {
    detailError.hidden = false;
    detailError.textContent = `${job.error.code}: ${job.error.message}`;
  } else {
    detailError.hidden = true;
    detailError.textContent = "";
  }

  const clips = job.clips || [];
  clipsList.replaceChildren();
  for (const clip of clips) {
    clipsList.append(renderClip(clip, job.id));
  }

  const finished = job.status === "done";
  exportActions.hidden = !finished || clips.length === 0;
  if (finished) {
    for (const link of exportActions.querySelectorAll("[data-export]")) {
      const format = link.dataset.export;
      const path = `/api/analyses/${encodeURIComponent(job.id)}/export?format=${format}`;
      link.href = path;
      link.onclick = (event) => {
        event.preventDefault();
        const extension = format === "spec" ? "json" : format;
        downloadFile(path, `analisis-${String(job.id).slice(0, 8)}.${extension}`);
      };
    }
  }

  if (finished && clips.length === 0) {
    clipsEmpty.hidden = false;
    clipsEmpty.textContent =
      "No se encontraron clips con esos parámetros. Prueba otra duración o más clips.";
  } else if (!finished) {
    clipsEmpty.hidden = false;
    clipsEmpty.textContent =
      job.status === "error"
        ? "El análisis terminó con error."
        : "El análisis está en curso. El resultado aparecerá aquí.";
  } else {
    clipsEmpty.hidden = true;
  }

  applyFlags();
  void hydrateRenders(job.id);
}

function renderClip(clip, analysisId) {
  const fragment = clipTemplate.content.cloneNode(true);
  const card = fragment.querySelector(".clip-card");

  card.querySelector(".clip-rank").textContent = String(clip.rank);
  card.querySelector(".clip-hook").textContent = clip.hook;
  card.querySelector(".clip-time").textContent =
    `${clip.start_time} – ${clip.end_time} · ${formatDuration(clip.duration_seconds)}`;
  card.querySelector(".clip-score").textContent =
    `Score ${Math.round((clip.score || 0) * 100)}%`;
  card.querySelector(".clip-caption").textContent = clip.caption_text;
  card.querySelector(".clip-reason").textContent = clip.reason;

  const tags = card.querySelector(".hashtags");
  for (const tag of clip.hashtags || []) {
    const item = document.createElement("li");
    item.textContent = tag;
    tags.append(item);
  }

  card
    .querySelector(".copy-hook")
    .addEventListener("click", () => copyText(clip.hook, "Gancho"));
  card
    .querySelector(".copy-caption")
    .addEventListener("click", () => copyText(clip.caption_text, "Texto"));

  const srt = card.querySelector(".clip-srt");
  const srtPath = `/api/analyses/${encodeURIComponent(analysisId)}/clips/${encodeURIComponent(clip.id)}/srt`;
  srt.href = srtPath;
  srt.hidden = !flagEnabled("export_srt");
  srt.onclick = (event) => {
    event.preventDefault();
    downloadFile(srtPath, `${clip.id}.srt`);
  };

  card.dataset.clipId = clip.id;
  setupRenderControls(card, clip, analysisId);

  return fragment;
}

/* ------------------------------------------------------------------ */
/* Renderizado de clips                                                */
/* ------------------------------------------------------------------ */

function renderElements(card) {
  return {
    controls: card.querySelector(".render-controls"),
    pathLabel: card.querySelector(".render-path-label"),
    pathInput: card.querySelector(".render-path"),
    sourceNote: card.querySelector(".render-source"),
    button: card.querySelector(".render-btn"),
    progressWrap: card.querySelector(".render-progress"),
    progressBar: card.querySelector(".render-progress-bar"),
    stage: card.querySelector(".render-stage"),
    result: card.querySelector(".render-result"),
    video: card.querySelector(".render-video"),
    thumb: card.querySelector(".render-thumb"),
    download: card.querySelector(".render-download"),
    thumbDownload: card.querySelector(".render-thumb-download"),
    deleteBtn: card.querySelector(".render-delete"),
    status: card.querySelector(".render-status"),
  };
}

function setupRenderControls(card, clip, analysisId) {
  const els = renderElements(card);
  const job = state.currentJob;
  if (job && job.source_path) {
    els.pathLabel.hidden = true;
    els.sourceNote.hidden = false;
    els.sourceNote.textContent = `Origen automático: ${job.source_path}`;
  }

  els.button.addEventListener("click", async () => {
    const videoPath = els.pathInput.value.trim();
    if (!videoPath && !(state.currentJob && state.currentJob.source_path)) {
      setStatus(
        els.status,
        "Indica la ruta del video de origen para renderizar.",
        "error",
      );
      return;
    }

    els.button.disabled = true;
    setStatus(els.status, "Enviando render…");
    els.progressWrap.hidden = false;
    els.progressBar.value = 0;
    els.stage.textContent = "en cola";
    els.result.hidden = true;

    const body = {};
    if (videoPath) {
      body.video_path = videoPath;
    }
    try {
      const accepted = await api(
        `/api/analyses/${encodeURIComponent(analysisId)}/clips/${encodeURIComponent(clip.id)}/render`,
        { method: "POST", body: JSON.stringify(body) },
      );
      card.dataset.renderId = accepted.id;
      setStatus(els.status, "Render encolado.");
      watchRender(accepted.id, card);
    } catch (error) {
      els.button.disabled = false;
      els.progressWrap.hidden = true;
      setStatus(els.status, describeError(error), "error");
    }
  });

  els.deleteBtn.addEventListener("click", async () => {
    const renderId = card.dataset.renderId;
    if (!renderId) {
      return;
    }
    if (!window.confirm("¿Borrar el video renderizado y su miniatura?")) {
      return;
    }
    try {
      await api(`/api/renders/${encodeURIComponent(renderId)}`, {
        method: "DELETE",
      });
      delete card.dataset.renderId;
      resetRenderCard(card);
      setStatus(els.status, "Render borrado.");
      showToast("Render borrado.");
    } catch (error) {
      setStatus(els.status, describeError(error), "error");
    }
  });

  els.download.addEventListener("click", (event) => {
    event.preventDefault();
    if (els.download.dataset.path) {
      downloadFile(
        els.download.dataset.path,
        `${clip.id}-${String(card.dataset.renderId || "").slice(0, 8)}.mp4`,
      );
    }
  });
  els.thumbDownload.addEventListener("click", (event) => {
    event.preventDefault();
    if (els.thumbDownload.dataset.path) {
      downloadFile(
        els.thumbDownload.dataset.path,
        `${clip.id}-${String(card.dataset.renderId || "").slice(0, 8)}.jpg`,
      );
    }
  });
}

function resetRenderCard(card) {
  const els = renderElements(card);
  els.button.disabled = false;
  els.progressWrap.hidden = true;
  els.progressBar.value = 0;
  els.stage.textContent = "";
  els.result.hidden = true;
  els.video.removeAttribute("src");
  els.video.load();
  els.thumb.removeAttribute("src");
  els.thumb.hidden = true;
  els.download.dataset.path = "";
  els.thumbDownload.dataset.path = "";
  els.download.hidden = true;
  els.thumbDownload.hidden = true;
  els.deleteBtn.hidden = true;
}

async function fetchObjectUrl(path) {
  const headers = new Headers();
  if (state.apiKey) {
    headers.set("X-API-Key", state.apiKey);
  }
  const response = await fetch(path, { headers });
  if (!response.ok) {
    throw new ApiError(response.status, null);
  }
  return URL.createObjectURL(await response.blob());
}

async function attachMedia(element, path) {
  if (!path) {
    element.removeAttribute("src");
    element.hidden = true;
    return;
  }
  if (!state.apiKey) {
    element.src = path;
    element.hidden = false;
    return;
  }
  try {
    element.src = await fetchObjectUrl(path);
    element.hidden = false;
  } catch {
    element.hidden = true;
  }
}

function applyRenderRecord(card, record) {
  if (!card || !record) {
    return;
  }
  const els = renderElements(card);
  card.dataset.renderId = record.id;
  const active = record.status === "queued" || record.status === "running";

  els.button.disabled = active;
  els.progressWrap.hidden = !active;
  if (active) {
    const value = Math.max(0, Math.min(100, Number(record.progress) || 0));
    els.progressBar.value = value;
    els.stage.textContent = record.stage
      ? `${value}% · ${record.stage}`
      : `${value}%`;
    setStatus(els.status, "Renderizando…");
  }

  if (record.status === "error") {
    els.result.hidden = true;
    const message = record.error
      ? `${record.error.code}: ${record.error.message}`
      : "El renderizado falló.";
    setStatus(els.status, message, "error");
    return;
  }

  if (record.status !== "done") {
    return;
  }

  els.progressWrap.hidden = true;
  els.result.hidden = false;
  els.button.disabled = false;
  els.button.textContent = "Volver a renderizar";
  setStatus(els.status, "Render listo.", "success");

  void attachMedia(els.video, record.download_url);
  void attachMedia(els.thumb, record.thumbnail_url);

  els.download.dataset.path = record.download_url || "";
  els.download.hidden = !record.download_url;
  els.thumbDownload.dataset.path = record.thumbnail_url || "";
  els.thumbDownload.hidden = !record.thumbnail_url;
  els.deleteBtn.hidden = false;
}

function stopRenderWatchers() {
  for (const cleanup of state.renderWatchers) {
    try {
      cleanup();
    } catch {
      /* ignorado */
    }
  }
  state.renderWatchers = [];
}

function watchRender(renderId, card) {
  let source = null;
  let timer = null;
  let stopped = false;

  const cleanup = () => {
    if (stopped) {
      return;
    }
    stopped = true;
    if (source) {
      source.close();
      source = null;
    }
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };
  state.renderWatchers.push(cleanup);

  const apply = (data) => {
    if (!data) {
      return;
    }
    applyRenderRecord(card, data);
    if (data.status === "done" || data.status === "error") {
      cleanup();
    }
  };

  if (
    flagEnabled("sse_progress") &&
    !state.apiKey &&
    typeof EventSource !== "undefined"
  ) {
    source = new EventSource(
      `/api/renders/${encodeURIComponent(renderId)}/events`,
    );
    const handleEvent = (event) => {
      try {
        apply(JSON.parse(event.data));
      } catch {
        /* evento ilegible */
      }
    };
    source.addEventListener("progress", handleEvent);
    source.addEventListener("done", handleEvent);
    source.addEventListener("error", (event) => {
      if (event && typeof event.data === "string") {
        handleEvent(event);
        return;
      }
      if (source) {
        source.close();
        source = null;
      }
      if (!stopped) {
        timer = setTimeout(tick, 500);
      }
    });
    return;
  }

  const tick = async () => {
    if (stopped) {
      return;
    }
    try {
      const record = await api(`/api/renders/${encodeURIComponent(renderId)}`);
      apply(record);
      if (!stopped) {
        timer = setTimeout(tick, 1000);
      }
    } catch (error) {
      cleanup();
      const els = renderElements(card);
      els.button.disabled = false;
      els.progressWrap.hidden = true;
      setStatus(els.status, describeError(error), "error");
    }
  };

  function scheduleRenderPoll() {
    if (!stopped) {
      timer = setTimeout(tick, 500);
    }
  }

  scheduleRenderPoll();
}

async function hydrateRenders(analysisId) {
  if (!analysisId) {
    return;
  }
  try {
    const data = await api(
      `/api/renders?job_id=${encodeURIComponent(analysisId)}&limit=100`,
    );
    const seen = new Set();
    for (const record of data.items || []) {
      if (seen.has(record.clip_id)) {
        continue;
      }
      seen.add(record.clip_id);
      const card = clipsList.querySelector(
        `.clip-card[data-clip-id="${record.clip_id}"]`,
      );
      if (card) {
        applyRenderRecord(card, record);
      }
    }
  } catch {
    /* el historial de renders es opcional */
  }
}

function closeDetail() {
  state.activeId = null;
  state.currentJob = null;
  stopWatching();
  stopRenderWatchers();
  detail.hidden = true;
  markActiveHistory();
}

/* ------------------------------------------------------------------ */
/* Análisis                                                            */
/* ------------------------------------------------------------------ */

function readTranscript() {
  const raw = transcriptText.value.trim();
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`El JSON no es válido: ${error.message}`);
  }
}

async function handleSubmit(event) {
  event.preventDefault();
  setStatus(formStatus, "");

  let transcript;
  try {
    transcript = readTranscript();
  } catch (error) {
    setStatus(formStatus, error.message, "error");
    return;
  }
  if (transcript === null) {
    setStatus(
      formStatus,
      "Carga un archivo o pega el JSON de la transcripción.",
      "error",
    );
    return;
  }

  const minDuration = Number(minDurationInput.value);
  const maxDuration = Number(maxDurationInput.value);
  if (!(maxDuration > minDuration)) {
    setStatus(
      formStatus,
      "La duración máxima debe ser mayor que la mínima.",
      "error",
    );
    return;
  }

  const payload = {
    transcript,
    platform: platformSelect.value,
    max_clips: Number(maxClipsInput.value),
    use_llm: useLlmInput.checked,
    min_duration: minDuration,
    max_duration: maxDuration,
  };

  analyzeBtn.disabled = true;
  setStatus(formStatus, "Enviando transcripción…");
  try {
    const accepted = await api("/api/analyses", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setStatus(
      formStatus,
      "Análisis encolado. El progreso se actualiza abajo.",
      "success",
    );
    state.activeId = accepted.id;
    await openDetail(accepted.id, { focus: true });
    await loadHistory();
  } catch (error) {
    setStatus(formStatus, describeError(error), "error");
  } finally {
    analyzeBtn.disabled = false;
  }
}

/* ------------------------------------------------------------------ */
/* Transcripción local con Whisper                                     */
/* ------------------------------------------------------------------ */

function selectedMediaFile() {
  return videoFile.files && videoFile.files[0] ? videoFile.files[0] : null;
}

function resetTranscriptionResult() {
  transcribeResult.hidden = true;
  transcribeMeta.replaceChildren();
  state.transcription = null;
}

function showTranscriptionProgress(progress, stage) {
  const value = Math.max(0, Math.min(100, Number(progress) || 0));
  transcribeProgressWrap.hidden = false;
  transcribeProgress.value = value;
  transcribeProgress.textContent = `${value}%`;
  transcribeStage.textContent = stage ? `${value}% · ${stage}` : `${value}%`;
}

async function handleTranscribe(event) {
  event.preventDefault();
  const file = selectedMediaFile();
  const path = videoPath.value.trim();
  if (!file && !path) {
    setStatus(
      transcribeStatus,
      "Selecciona un video o indica una ruta local.",
      "error",
    );
    return;
  }

  resetTranscriptionResult();
  transcribeBtn.disabled = true;
  setStatus(transcribeStatus, "Enviando video…");
  showTranscriptionProgress(0, "en cola");

  const model = whisperModel.value;
  const language = whisperLanguage.value;
  try {
    let accepted;
    if (file) {
      const body = new FormData();
      body.append("file", file, file.name);
      body.append("model", model);
      body.append("language", language);
      accepted = await api("/api/transcriptions/upload", {
        method: "POST",
        body,
      });
    } else {
      accepted = await api("/api/transcriptions", {
        method: "POST",
        body: JSON.stringify({ path, model, language }),
      });
    }
    state.transcriptionId = accepted.id;
    setStatus(
      transcribeStatus,
      "Transcripción encolada. Puedes seguir usando la app mientras termina.",
    );
    watchTranscription(accepted.id);
  } catch (error) {
    setStatus(transcribeStatus, describeError(error), "error");
    transcribeBtn.disabled = false;
  }
}

function stopWatchingTranscription() {
  if (state.transcriptionEventSource) {
    state.transcriptionEventSource.close();
    state.transcriptionEventSource = null;
  }
  clearTimeout(state.transcriptionPollTimer);
  state.transcriptionPollTimer = null;
}

function watchTranscription(id) {
  stopWatchingTranscription();
  if (
    flagEnabled("sse_progress") &&
    !state.apiKey &&
    typeof EventSource !== "undefined"
  ) {
    watchTranscriptionWithSse(id);
  } else {
    scheduleTranscriptionPoll(id);
  }
}

function watchTranscriptionWithSse(id) {
  const source = new EventSource(
    `/api/transcriptions/${encodeURIComponent(id)}/events`,
  );
  state.transcriptionEventSource = source;

  const handleEvent = (event) => {
    let data = null;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (!data) {
      return;
    }
    showTranscriptionProgress(data.progress, data.stage);
    if (data.status === "done" || data.status === "error") {
      stopWatchingTranscription();
      finishTranscription(id);
    }
  };

  source.addEventListener("progress", handleEvent);
  source.addEventListener("done", handleEvent);
  source.addEventListener("error", (event) => {
    if (event && typeof event.data === "string") {
      handleEvent(event);
      return;
    }
    stopWatchingTranscription();
    scheduleTranscriptionPoll(id);
  });
}

function scheduleTranscriptionPoll(id) {
  clearTimeout(state.transcriptionPollTimer);
  const tick = async () => {
    if (state.transcriptionId !== id) {
      return;
    }
    try {
      const record = await api(
        `/api/transcriptions/${encodeURIComponent(id)}`,
      );
      showTranscriptionProgress(record.progress, record.stage);
      if (record.status === "queued" || record.status === "running") {
        state.transcriptionPollTimer = setTimeout(tick, 1000);
      } else {
        finishTranscription(id, record);
      }
    } catch (error) {
      setStatus(transcribeStatus, describeError(error), "error");
      transcribeBtn.disabled = false;
    }
  };
  state.transcriptionPollTimer = setTimeout(tick, 800);
}

async function finishTranscription(id, record = null) {
  try {
    const data =
      record ||
      (await api(`/api/transcriptions/${encodeURIComponent(id)}`));
    if (state.transcriptionId !== id) {
      return;
    }
    transcribeBtn.disabled = false;
    if (data.status === "error") {
      const message = data.error
        ? `${data.error.code}: ${data.error.message}`
        : "La transcripción falló.";
      setStatus(transcribeStatus, message, "error");
      resetTranscriptionResult();
      return;
    }
    state.transcription = data;
    showTranscriptionProgress(100, "listo");
    setStatus(transcribeStatus, "Transcripción lista.", "success");
    renderTranscriptionResult(data);
  } catch (error) {
    transcribeBtn.disabled = false;
    setStatus(transcribeStatus, describeError(error), "error");
  }
}

function renderTranscriptionResult(data) {
  const transcript = data.transcript;
  const segments = transcript && Array.isArray(transcript.segments)
    ? transcript.segments.length
    : 0;
  const words = transcript && Array.isArray(transcript.segments)
    ? transcript.segments.reduce(
        (total, segment) =>
          total + (Array.isArray(segment.words) ? segment.words.length : 0),
        0,
      )
    : 0;
  transcribeMeta.replaceChildren(
    metaItem("Archivo", data.filename),
    metaItem("Idioma", data.language || "—"),
    metaItem("Duración", formatDuration(data.duration) || "—"),
    metaItem("Segmentos", String(segments)),
    metaItem("Palabras", String(words)),
    metaItem("Modelo", data.model),
  );
  transcribeResult.hidden = false;
}

async function analyzeCurrentTranscription() {
  const data = state.transcription;
  if (!data || data.status !== "done") {
    setStatus(
      transcribeStatus,
      "Primero termina una transcripción para poder analizarla.",
      "error",
    );
    return;
  }

  const minDuration = Number(minDurationInput.value);
  const maxDuration = Number(maxDurationInput.value);
  if (
    !Number.isFinite(minDuration) ||
    !Number.isFinite(maxDuration) ||
    maxDuration <= minDuration
  ) {
    setStatus(
      transcribeStatus,
      "La duración máxima debe ser mayor que la mínima.",
      "error",
    );
    return;
  }

  analyzeTranscriptionBtn.disabled = true;
  try {
    const accepted = await api(
      `/api/transcriptions/${encodeURIComponent(data.id)}/analyze`,
      {
        method: "POST",
        body: JSON.stringify({
          platform: platformSelect.value,
          max_clips: Number(maxClipsInput.value),
          use_llm: useLlmInput.checked,
          min_duration: minDuration,
          max_duration: maxDuration,
        }),
      },
    );
    setStatus(transcribeStatus, "Análisis encolado.", "success");
    state.activeId = accepted.id;
    await openDetail(accepted.id, { focus: true });
    await loadHistory();
  } catch (error) {
    setStatus(transcribeStatus, describeError(error), "error");
  } finally {
    analyzeTranscriptionBtn.disabled = false;
  }
}

function loadTranscriptionJson() {
  const transcript = state.transcription && state.transcription.transcript;
  if (!transcript) {
    return;
  }
  transcriptText.value = JSON.stringify(transcript, null, 2);
  setStatus(
    formStatus,
    "Transcripción cargada en el editor. Ajusta las opciones y pulsa «Analizar transcripción».",
    "success",
  );
  const title = document.getElementById("upload-title");
  if (title) {
    title.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function copyTranscriptionJson() {
  const transcript = state.transcription && state.transcription.transcript;
  if (!transcript) {
    return;
  }
  copyText(JSON.stringify(transcript, null, 2), "JSON de la transcripción");
}

function handleVideoDrop(event) {
  event.preventDefault();
  videoDrop.classList.remove("is-active");
  const files = event.dataTransfer && event.dataTransfer.files;
  if (!files || !files.length) {
    return;
  }
  videoFile.files = files;
  setStatus(
    transcribeStatus,
    `Archivo «${files[0].name}» seleccionado.`,
    "success",
  );
}

function handleVideoFileChange() {
  const file = selectedMediaFile();
  if (file) {
    setStatus(
      transcribeStatus,
      `Archivo «${file.name}» seleccionado.`,
      "success",
    );
  }
}

function stopWatching() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
  clearTimeout(state.pollTimer);
  state.pollTimer = null;
}

function watchAnalysis(id) {
  stopWatching();
  if (
    flagEnabled("sse_progress") &&
    !state.apiKey &&
    typeof EventSource !== "undefined"
  ) {
    watchWithSse(id);
  } else {
    schedulePoll(id);
  }
}

function watchWithSse(id) {
  const source = new EventSource(
    `/api/analyses/${encodeURIComponent(id)}/events`,
  );
  state.eventSource = source;

  const handleEvent = (event) => {
    let data = null;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (!data) {
      return;
    }
    if (data.status === "done" || data.status === "error") {
      stopWatching();
      openDetail(id, { focus: false });
      loadHistory();
      loadHealth();
      return;
    }
    updateProgress(data);
  };

  source.addEventListener("progress", handleEvent);
  source.addEventListener("done", handleEvent);
  source.addEventListener("error", (event) => {
    if (event && typeof event.data === "string") {
      handleEvent(event);
      return;
    }
    stopWatching();
    schedulePoll(id);
  });
}

function updateProgress(data) {
  if (!state.currentJob || state.currentJob.id !== data.id) {
    return;
  }
  state.currentJob = {
    ...state.currentJob,
    status: data.status,
    progress: data.progress,
    stage: data.stage,
    updated_at: data.updated_at || state.currentJob.updated_at,
  };
  renderDetail(state.currentJob);
}

function schedulePoll(id) {
  clearTimeout(state.pollTimer);
  const tick = async () => {
    if (state.activeId !== id) {
      return;
    }
    try {
      const job = await api(`/api/analyses/${encodeURIComponent(id)}`);
      renderDetail(job);
      if (job.status === "queued" || job.status === "running") {
        state.pollTimer = setTimeout(tick, 1000);
      } else {
        await loadHistory();
        loadHealth();
      }
    } catch (error) {
      detailError.hidden = false;
      detailError.textContent = describeError(error);
    }
  };
  state.pollTimer = setTimeout(tick, 800);
}

async function deleteAnalysis(id) {
  const confirmed = window.confirm(
    "¿Borrar este análisis y todos sus clips? Esta acción no se puede deshacer.",
  );
  if (!confirmed) {
    return;
  }
  try {
    await api(`/api/analyses/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (state.activeId === id) {
      closeDetail();
    }
    showToast("Análisis borrado.");
    await loadHistory();
  } catch (error) {
    showToast(describeError(error));
  }
}

/* ------------------------------------------------------------------ */
/* Archivo de ejemplo y ajustes                                        */
/* ------------------------------------------------------------------ */

async function handleFileChange() {
  const file = transcriptFile.files && transcriptFile.files[0];
  if (!file) {
    return;
  }
  try {
    if (file.size > MAX_FILE_BYTES) {
      throw new Error("El archivo supera 2 MB. Divide la transcripción.");
    }
    const text = await file.text();
    transcriptText.value = text;
    setStatus(formStatus, `Archivo «${file.name}» cargado en el editor.`, "success");
  } catch (error) {
    setStatus(formStatus, error.message, "error");
  } finally {
    transcriptFile.value = "";
  }
}

function loadSample() {
  transcriptText.value = JSON.stringify(SAMPLE_TRANSCRIPT, null, 2);
  platformSelect.value = "tiktok";
  setStatus(formStatus, "Ejemplo cargado. Pulsa «Analizar transcripción».", "success");
}

function openSettings() {
  apiKeyInput.value = state.apiKey;
  settingsDialog.showModal();
  apiKeyInput.focus();
  loadFlags();
}

function saveSettings() {
  state.apiKey = apiKeyInput.value.trim();
  if (state.apiKey) {
    sessionStorage.setItem(STORAGE_KEY, state.apiKey);
    showToast("API key guardada en esta pestaña.");
  } else {
    sessionStorage.removeItem(STORAGE_KEY);
    showToast("API key borrada.");
  }
  loadHealth();
  loadConfig();
  loadHistory();
}

function clearSettings() {
  apiKeyInput.value = "";
  state.apiKey = "";
  sessionStorage.removeItem(STORAGE_KEY);
  showToast("API key borrada.");
}

/* ------------------------------------------------------------------ */
/* Inicialización                                                      */
/* ------------------------------------------------------------------ */

function init() {
  analysisForm.addEventListener("submit", handleSubmit);
  transcriptFile.addEventListener("change", handleFileChange);
  sampleBtn.addEventListener("click", loadSample);
  transcribeForm.addEventListener("submit", handleTranscribe);
  videoFile.addEventListener("change", handleVideoFileChange);
  videoDrop.addEventListener("dragover", (event) => {
    event.preventDefault();
    videoDrop.classList.add("is-active");
  });
  videoDrop.addEventListener("dragleave", () =>
    videoDrop.classList.remove("is-active"),
  );
  videoDrop.addEventListener("drop", handleVideoDrop);
  analyzeTranscriptionBtn.addEventListener("click", analyzeCurrentTranscription);
  loadTranscriptJsonBtn.addEventListener("click", loadTranscriptionJson);
  copyTranscriptJsonBtn.addEventListener("click", copyTranscriptionJson);
  refreshHistoryBtn.addEventListener("click", loadHistory);
  closeDetailBtn.addEventListener("click", closeDetail);
  openSettingsBtn.addEventListener("click", openSettings);
  settingsForm.addEventListener("submit", saveSettings);
  clearSettingsBtn.addEventListener("click", clearSettings);

  if (state.apiKey) {
    apiKeyInput.value = state.apiKey;
  }

  loadHealth();
  loadConfig();
  loadHistory();
}

init();
