"use strict";

// ---------------------------------------------------------------------------
// Configuración
// ---------------------------------------------------------------------------
const LIMITS = {
  title: 200,
  detail: 2000,
  offerMin: 10,
  offerMax: 8000,
  entriesPerSection: 50,
  fileBytes: 5 * 1024 * 1024,
  cvChars: 30_000, // el backend recorta el texto del CV a este máximo (MAX_TEXT_CHARS)
};

// Oferta ficticia para probar el flujo sin buscar una real.
const EXAMPLE_OFFER = `Desarrollador/a Backend Python — Empresa Ejemplo S.L.

Buscamos una persona para incorporarse a nuestro equipo de producto.

Requisitos:
- 3+ años de experiencia con Python
- Conocimientos de FastAPI o Django
- SQL y bases de datos relacionales
- Git y trabajo con control de versiones
- Inglés B2

Valorable: Docker, AWS, tests automatizados.`;

// Claves = las del schema Profile del backend.
const SECTIONS = [
  ["experience", "Experiencia"],
  ["education", "Formación"],
  ["courses", "Cursos"],
  ["skills", "Skills"],
  ["languages", "Idiomas"],
  ["achievements", "Logros"],
];

// Claves = los valores de OfferRequirement.status del backend.
const STATUS = {
  OK: { label: "Cumple", cls: "ok" },
  Partial: { label: "Parcial", cls: "partial" },
  KO: { label: "No cumple", cls: "ko" },
};

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------
let profile = null;     // perfil en revisión (se usará en el paso 3, cuando el grafo pida revisión humana)
let editing = null;     // { section, index } ; index === null => entrada nueva
let busy = false;
let threadId = null;    // identificador de la ejecución del grafo (lo devuelve POST /match)

// ---------------------------------------------------------------------------
// Utilidades DOM (todo el contenido dinámico se pinta como texto, nunca HTML)
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function showMessage(text, isError = false) {
  const el = $("message");
  el.textContent = text;
  el.classList.toggle("error", isError);
  el.hidden = false;
}

function clearMessage() {
  $("message").hidden = true;
  $("message").textContent = "";
}

function setBusy(value) {
  busy = value;
  document.body.style.cursor = value ? "progress" : "";
  updateUploadButton();
  updateOfferButton();
  // El botón de inicio queda bloqueado mientras haya una ejecución en marcha o esperando revisión.
  $("start-btn").disabled = value || threadId !== null;
  $("cancel-review-btn").disabled = value;
  $("confirm-btn").disabled = value || editing !== null || !profile || totalEntries() === 0;
  $("back-cv-btn").disabled = value;
  $("back-offer-btn").disabled = value;
  $("delete-btn").disabled = value;
  // Evita cambiar el archivo o la oferta mientras la petición está en curso.
  $("cv-file").disabled = value;
  $("consent").disabled = value;
  $("offer-text").readOnly = value;
  $("example-btn").disabled = value;
}

// ---------------------------------------------------------------------------
// Indicador de carga
// ---------------------------------------------------------------------------
// Los mensajes dependen del tiempo transcurrido: el servidor no informa del progreso
// real, así que no se muestra ningún porcentaje (sería inventado).
const LOADING_STEPS = {
  // POST /match: el grafo extrae el perfil y se detiene a pedir revisión.
  match: [
    [0, "Leyendo tu CV y la oferta…"],
    [8, "Extrayendo tu perfil…"],
    [30, "Casi listo. Puede tardar hasta un minuto…"],
    [60, "Está tardando más de lo habitual. Sigue en marcha…"],
  ],
  // POST /match/{thread_id}/resume: el grafo continúa con el perfil confirmado.
  resume: [
    [0, "Preparando la comparación…"],
    [8, "Comparando tu perfil con cada requisito…"],
    [30, "Verificando las evidencias…"],
    [55, "Casi listo. Puede tardar hasta un minuto…"],
    [80, "Está tardando más de lo habitual. Sigue en marcha…"],
  ],
};

// Muestra el indicador dentro de `container` y devuelve la función que lo detiene.
function startLoading(container, steps) {
  const label = h("span", { class: "loading-label" }, steps[0][1]);
  const time = h("span", { class: "loading-time", "aria-hidden": "true" }, "0 s");
  container.replaceChildren(
    h("div", { class: "spinner", "aria-hidden": "true" }),
    h("div", { class: "loading-text" }, label, time, h("div", { class: "loading-bar", "aria-hidden": "true" })),
  );
  container.hidden = false;

  const startedAt = Date.now();
  const tick = () => {
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    time.textContent = `${seconds} s`;
    const current = steps.filter(([from]) => seconds >= from).at(-1)[1];
    // Solo se escribe si cambia, para que un lector de pantalla no repita el aviso.
    if (label.textContent !== current) label.textContent = current;
  };
  const timerId = setInterval(tick, 1000);

  return () => {
    clearInterval(timerId);
    container.hidden = true;
    container.replaceChildren();
  };
}

// ---------------------------------------------------------------------------
// Capa de API
// ---------------------------------------------------------------------------
const SLOW_TIMEOUT_MS = 120_000; // análisis del paso 3 (el grafo llama varias veces al LLM)

// Error con el código HTTP, para poder reaccionar a casos concretos (por ejemplo, 404 al reanudar).
function httpError(message, status) {
  const err = new Error(message);
  err.status = status;
  return err;
}

async function request(path, options = {}) {
  const { timeoutMs = 30_000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res;
  try {
    res = await fetch(path, { ...fetchOptions, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("La operación ha tardado demasiado. Inténtalo de nuevo.");
    }
    throw new Error("No se ha podido conectar con el servidor. Comprueba tu conexión.");
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    let detail = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      // la respuesta no trae JSON
    }
    // Los errores propios del backend (413, 415, 422, 502...) traen un mensaje en español.
    // En un 500 no se muestra el detalle interno.
    if (typeof detail === "string" && res.status !== 500) throw httpError(detail, res.status);

    let msg = `Error ${res.status}.`;
    if (res.status === 401) msg = "Código de acceso inválido.";
    else if (res.status === 422) msg = "Los datos enviados no son válidos. Revisa los límites de longitud.";
    else if (res.status === 429) msg = "Has alcanzado el límite diario de análisis.";
    else if (res.status >= 500) msg = "Error del servidor. Inténtalo de nuevo en un momento.";
    throw httpError(msg, res.status);
  }
  return res.status === 204 ? null : res.json();
}

const api = {
  // Paso 1: el backend valida el archivo y guarda su texto. No llama al LLM.
  async uploadCv(file) {
    const body = new FormData();
    body.append("file", file);
    // Sin cabecera Content-Type: el navegador la genera con el boundary.
    return request("/cv", { method: "POST", body });
  },

  // Paso 2: el backend valida la oferta y guarda su texto. No llama al LLM.
  async uploadOffer(offer) {
    return request("/offer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ offer }),
    });
  },

  // Paso 3a: lanza el grafo con el CV y la oferta ya guardados.
  // Responde { thread_id, profile }: el grafo se detiene a la espera de la revisión.
  async startMatch() {
    return request("/match", { method: "POST", timeoutMs: SLOW_TIMEOUT_MS });
  },

  // Paso 3b: reanuda el grafo con el perfil confirmado. Responde { score, requirements }.
  async resumeMatch(id, p) {
    return request(`/match/${encodeURIComponent(id)}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: p }),
      timeoutMs: SLOW_TIMEOUT_MS,
    });
  },

  // Borra el CV, la oferta y el perfil del usuario.
  async deleteProfile() {
    return request("/profile", { method: "DELETE" });
  },
};

// ---------------------------------------------------------------------------
// Navegación entre pasos
// ---------------------------------------------------------------------------
function showStep(n) {
  for (const section of document.querySelectorAll("main > section")) {
    section.hidden = Number(section.dataset.step) !== n;
  }
  for (const li of $("steps").children) {
    const step = Number(li.dataset.step);
    li.classList.toggle("done", step < n);
    if (step === n) li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  }
  window.scrollTo({ top: 0 });
}

// ---------------------------------------------------------------------------
// Paso 1: subir el CV
// ---------------------------------------------------------------------------
const DOC_MESSAGE = "Los archivos .doc (Word antiguo) no se admiten. Guárdalo como DOCX o PDF.";

// Resultado de la última comprobación del archivo elegido (extensión, tamaño y contenido).
let fileCheck = { file: null, ok: false };

// Lee los primeros bytes para saber qué es el archivo de verdad, no lo que dice su nombre.
// Es solo una ayuda para el usuario: la validación que cuenta es la del servidor.
async function sniffFileType(file) {
  const head = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  const startsWith = (...bytes) => bytes.every((b, i) => head[i] === b);
  if (startsWith(0x25, 0x50, 0x44, 0x46)) return "pdf"; // %PDF
  if (startsWith(0x50, 0x4b, 0x03, 0x04)) return "zip"; // PK.. (un DOCX es un ZIP)
  if (startsWith(0xd0, 0xcf, 0x11, 0xe0)) return "doc"; // Word 97-2003
  return null;
}

async function validateFile(file) {
  if (!file) return "Selecciona un archivo.";
  const name = file.name.toLowerCase();
  if (name.endsWith(".doc")) return DOC_MESSAGE;
  const isPdf = name.endsWith(".pdf");
  const isDocx = name.endsWith(".docx");
  if (!isPdf && !isDocx) return "Solo se admiten archivos PDF o DOCX.";
  if (file.size === 0) return "El archivo está vacío.";
  if (file.size > LIMITS.fileBytes) return "El archivo supera los 5 MB.";

  const kind = await sniffFileType(file);
  if (kind === "doc") return DOC_MESSAGE;
  if (isPdf && kind !== "pdf") return "El archivo no es un PDF válido.";
  if (isDocx && kind !== "zip") return "El archivo no es un DOCX válido.";
  return null;
}

function updateUploadButton() {
  const file = $("cv-file").files[0];
  const fileOk = Boolean(file) && fileCheck.file === file && fileCheck.ok;
  $("upload-btn").disabled = busy || !fileOk || !$("consent").checked;
}

async function onFileChange() {
  const file = $("cv-file").files[0];
  fileCheck = { file, ok: false };
  const el = $("file-error");
  el.hidden = true;
  updateUploadButton();
  if (!file) return;

  const error = await validateFile(file);
  if ($("cv-file").files[0] !== file) return; // el usuario eligió otro archivo mientras tanto
  fileCheck = { file, ok: error === null };
  el.textContent = error || "";
  el.hidden = !error;
  updateUploadButton();
}

async function onUploadSubmit(event) {
  event.preventDefault();
  const file = $("cv-file").files[0];
  if (busy || !file || fileCheck.file !== file || !fileCheck.ok || !$("consent").checked) return;

  clearMessage();
  setBusy(true);
  $("upload-btn").textContent = "Subiendo…";
  try {
    const data = await api.uploadCv(file);
    showStep(2);
    let text = `CV cargado (${data.characters} caracteres de texto).`;
    // Si llega justo al máximo, casi seguro que el CV era más largo y se ha recortado.
    if (data.characters >= LIMITS.cvChars) {
      text += ` Se ha recortado a ${LIMITS.cvChars.toLocaleString("es-ES")} caracteres.`;
    }
    showMessage(text);
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    $("upload-btn").textContent = "Subir CV";
    setBusy(false);
  }
}

// Garantiza que existen las seis secciones aunque el backend omita alguna.
function normalizeProfile(p) {
  const result = {};
  for (const [key] of SECTIONS) {
    result[key] = Array.isArray(p?.[key])
      ? p[key].map((e) => ({ title: String(e.title ?? ""), detail: String(e.detail ?? "") }))
      : [];
  }
  return result;
}

// ---------------------------------------------------------------------------
// Revisión humana (HITL): editar, añadir y quitar (paso 3, cuando el grafo se detiene a pedir revisión)
// ---------------------------------------------------------------------------
function totalEntries() {
  return SECTIONS.reduce((sum, [key]) => sum + profile[key].length, 0);
}

function isEditing(section, index) {
  return editing !== null && editing.section === section && editing.index === index;
}

function startEdit(section, index) {
  editing = { section, index };
  renderReview();
}

function cancelEdit() {
  editing = null;
  renderReview();
}

function removeEntry(section, index) {
  profile[section].splice(index, 1);
  editing = null;
  renderReview();
}

function renderEntryForm(section, index, entry) {
  const titleInput = h("input", { type: "text", maxlength: LIMITS.title, value: entry.title, id: "edit-title" });
  const detailInput = h("textarea", { rows: 3, maxlength: LIMITS.detail, id: "edit-detail" });
  detailInput.value = entry.detail;
  const error = h("p", { class: "field-error", hidden: true });

  const save = () => {
    const title = titleInput.value.trim();
    const detail = detailInput.value.trim();
    if (title.length < 1 || title.length > LIMITS.title) {
      error.textContent = `El título es obligatorio (máximo ${LIMITS.title} caracteres).`;
      error.hidden = false;
      titleInput.focus();
      return;
    }
    if (detail.length > LIMITS.detail) {
      error.textContent = `El detalle admite como máximo ${LIMITS.detail} caracteres.`;
      error.hidden = false;
      detailInput.focus();
      return;
    }
    if (index === null) profile[section].push({ title, detail });
    else profile[section][index] = { title, detail };
    editing = null;
    renderReview();
  };

  const form = h(
    "li",
    { class: "entry entry-form" },
    h("label", { for: "edit-title" }, "Título"),
    titleInput,
    h("label", { for: "edit-detail" }, "Detalle (opcional)"),
    detailInput,
    error,
    h(
      "div",
      { class: "actions" },
      h("button", { type: "button", class: "btn primary small", onclick: save }, "Guardar"),
      h("button", { type: "button", class: "btn small", onclick: cancelEdit }, "Cancelar"),
    ),
  );
  titleInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      save();
    }
  });
  return form;
}

function renderEntry(section, index, entry) {
  if (isEditing(section, index)) return renderEntryForm(section, index, entry);
  return h(
    "li",
    { class: "entry" },
    h("div", { class: "entry-text" }, h("strong", {}, entry.title), entry.detail ? h("p", {}, entry.detail) : null),
    h(
      "div",
      { class: "entry-actions" },
      h("button", { type: "button", class: "btn small", onclick: () => startEdit(section, index) }, "Editar"),
      h("button", { type: "button", class: "btn small", onclick: () => removeEntry(section, index) }, "Quitar"),
    ),
  );
}

function renderReview() {
  const container = $("review-sections");
  container.replaceChildren();

  for (const [key, label] of SECTIONS) {
    const entries = profile[key];
    const adding = isEditing(key, null);
    const full = entries.length >= LIMITS.entriesPerSection;

    const list = h("ul", { class: "entries" });
    entries.forEach((entry, i) => list.append(renderEntry(key, i, entry)));
    if (adding) list.append(renderEntryForm(key, null, { title: "", detail: "" }));
    if (entries.length === 0 && !adding) list.append(h("li", { class: "empty" }, "Sin entradas."));

    container.append(
      h(
        "div",
        { class: "profile-section" },
        h(
          "div",
          { class: "profile-section-head" },
          h("h3", {}, `${label} (${entries.length})`),
          h(
            "button",
            {
              type: "button",
              class: "btn small",
              disabled: full || editing !== null,
              title: full ? `Máximo ${LIMITS.entriesPerSection} entradas` : null,
              onclick: () => startEdit(key, null),
            },
            "+ Añadir",
          ),
        ),
        list,
      ),
    );
  }

  const total = totalEntries();
  $("review-summary").textContent = editing
    ? "Termina de editar la entrada abierta para poder confirmar."
    : total === 0
      ? "El perfil está vacío. Añade al menos una entrada para continuar."
      : `${total} entradas en total.`;
  $("confirm-btn").disabled = busy || editing !== null || total === 0;

  const firstInput = container.querySelector(".entry-form input");
  if (firstInput) firstInput.focus();
}

// Vuelve al paso 1 y limpia el formulario del CV.
function resetUploadForm() {
  profile = null;
  editing = null;
  $("cv-file").value = "";
  fileCheck = { file: null, ok: false };
  $("file-error").hidden = true;
  updateUploadButton();
}

function onBackToCv() {
  clearMessage();
  resetUploadForm();
  showStep(1);
}

// ---------------------------------------------------------------------------
// Paso 2: oferta
// ---------------------------------------------------------------------------
function offerLength() {
  return $("offer-text").value.trim().length;
}

function updateOfferButton() {
  const len = offerLength();
  $("offer-counter").textContent = `${$("offer-text").value.length} / ${LIMITS.offerMax}`;
  $("offer-btn").disabled = busy || len < LIMITS.offerMin || len > LIMITS.offerMax;
}

async function onOfferSubmit(event) {
  event.preventDefault();
  const offer = $("offer-text").value.trim();
  if (busy || offer.length < LIMITS.offerMin || offer.length > LIMITS.offerMax) return;

  clearMessage();
  setBusy(true);
  $("offer-btn").textContent = "Guardando…";
  try {
    const data = await api.uploadOffer(offer);
    resetStep3();
    showStep(3);
    showMessage(`Oferta cargada (${data.characters} caracteres de texto).`);
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    $("offer-btn").textContent = "Continuar";
    setBusy(false);
  }
}

// ---------------------------------------------------------------------------
// Paso 3: análisis (el grafo del backend) y resultado
// ---------------------------------------------------------------------------
// Estado inicial del paso 3: botón de inicio visible, sin revisión ni resultado.
function resetStep3() {
  threadId = null;
  profile = null;
  editing = null;
  $("start-phase").hidden = false;
  $("start-btn").disabled = busy; // sin ejecución pendiente, el botón vuelve a estar disponible
  $("review-phase").hidden = true;
  $("result").hidden = true;
}

// Paso 3a: el grafo extrae el perfil y se detiene; mostramos el perfil para revisarlo.
async function onStartMatch() {
  // Un solo análisis a la vez: se ignora si ya hay uno en curso o pendiente de revisión.
  if (busy || threadId !== null) return;
  $("start-btn").disabled = true; // se bloquea en el mismo instante de la pulsación
  clearMessage();
  setBusy(true);
  $("start-btn").textContent = "Analizando…";
  const stopLoading = startLoading($("match-loading"), LOADING_STEPS.match);
  try {
    const data = await api.startMatch();
    threadId = data.thread_id;
    profile = normalizeProfile(data.profile);
    editing = null;
    $("start-phase").hidden = true;
    $("review-phase").hidden = false;
    renderReview();
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    stopLoading();
    $("start-btn").textContent = "Iniciar análisis";
    setBusy(false);
  }
}

// Paso 3b: enviamos el perfil confirmado (o editado) y el grafo continúa hasta el resultado.
async function onConfirm() {
  if (busy || editing !== null || !profile || !threadId || totalEntries() === 0) return;
  $("confirm-btn").disabled = true; // se bloquea en el mismo instante de la pulsación
  clearMessage();
  setBusy(true);
  $("confirm-btn").textContent = "Analizando…";
  const stopLoading = startLoading($("resume-loading"), LOADING_STEPS.resume);
  try {
    const result = await api.resumeMatch(threadId, profile);
    renderResult(result);
    $("review-phase").hidden = true;
    $("result").hidden = false;
    threadId = null; // la ejecución ha terminado
    profile = null;  // sin perfil, "Confirmar" queda bloqueado hasta la próxima revisión
  } catch (err) {
    if (err.status === 404 || err.status === 409) {
      // La ejecución ya no existe (por ejemplo, el servidor se reinició): hay que empezar de nuevo.
      resetStep3();
      showMessage("La revisión ha caducado. Vuelve a iniciar el análisis.", true);
    } else {
      showMessage(err.message, true);
    }
  } finally {
    stopLoading();
    $("confirm-btn").textContent = "Confirmar y analizar";
    setBusy(false);
    if (!$("review-phase").hidden) renderReview();
  }
}

// Descarta la revisión y vuelve al botón de inicio.
function onCancelReview() {
  if (busy) return;
  clearMessage();
  resetStep3();
}

function renderResult(result) {
  const score = Math.max(0, Math.min(100, Number(result.score) || 0));
  $("score-value").textContent = `${score}%`;
  $("score-fill").style.width = `${score}%`;
  $("score-meter").setAttribute("aria-valuenow", String(score));

  const list = $("requirements");
  list.replaceChildren();
  for (const req of result.requirements ?? []) {
    const status = STATUS[req.status] ?? { label: String(req.status), cls: "ko" };
    list.append(
      h(
        "li",
        { class: "requirement" },
        h(
          "div",
          { class: "requirement-head" },
          h("span", { class: "requirement-text" }, req.text),
          h("span", { class: `badge ${status.cls}` }, status.label),
        ),
        h("p", { class: "evidence" }, req.evidence ? `Evidencia: ${req.evidence}` : "Sin evidencia en tu perfil."),
      ),
    );
  }
}

function onUseExample() {
  $("offer-text").value = EXAMPLE_OFFER;
  updateOfferButton();
  $("offer-text").focus();
}

function onAnotherOffer() {
  $("offer-text").value = "";
  updateOfferButton();
  clearMessage();
  resetStep3();
  showStep(2);
}

function onBackToOffer() {
  clearMessage();
  showStep(2);
}

// ---------------------------------------------------------------------------
// Borrar datos
// ---------------------------------------------------------------------------
async function onDelete() {
  if (busy) return;
  if (!window.confirm("Se borrarán tu CV, la oferta y tu perfil. Esta acción no se puede deshacer. ¿Continuar?")) return;
  clearMessage();
  setBusy(true);
  try {
    await api.deleteProfile();
    resetUploadForm();
    resetStep3();
    $("consent").checked = false;
    $("offer-text").value = "";
    updateOfferButton();
    showStep(1);
    showMessage("Tus datos se han borrado.");
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    setBusy(false);
  }
}

// ---------------------------------------------------------------------------
// Arranque
// ---------------------------------------------------------------------------
function init() {
  $("cv-file").addEventListener("change", onFileChange);
  $("consent").addEventListener("change", updateUploadButton);
  $("upload-form").addEventListener("submit", onUploadSubmit);
  $("offer-text").addEventListener("input", updateOfferButton);
  $("offer-form").addEventListener("submit", onOfferSubmit);
  $("example-btn").addEventListener("click", onUseExample);
  $("back-cv-btn").addEventListener("click", onBackToCv);
  $("back-offer-btn").addEventListener("click", onBackToOffer);
  $("start-btn").addEventListener("click", onStartMatch);
  $("confirm-btn").addEventListener("click", onConfirm);
  $("cancel-review-btn").addEventListener("click", onCancelReview);
  $("another-btn").addEventListener("click", onAnotherOffer);
  $("delete-btn").addEventListener("click", onDelete);
  updateUploadButton();
  updateOfferButton();
  showStep(1);
}

init();