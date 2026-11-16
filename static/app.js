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
let profile = null;     // perfil en revisión o confirmado
let editing = null;     // { section, index } ; index === null => entrada nueva
let busy = false;

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
  $("confirm-btn").disabled = value || editing !== null;
  $("delete-btn").disabled = value;
}

// ---------------------------------------------------------------------------
// Capa de API
// ---------------------------------------------------------------------------
async function request(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      // la respuesta no trae JSON
    }
    // Los errores propios del backend (413, 415, 422, 502...) traen un mensaje en español.
    // En un 500 no se muestra el detalle interno.
    if (typeof detail === "string" && res.status !== 500) throw new Error(detail);

    let msg = `Error ${res.status}.`;
    if (res.status === 401) msg = "Código de acceso inválido.";
    else if (res.status === 422) msg = "Los datos enviados no son válidos. Revisa los límites de longitud.";
    else if (res.status === 429) msg = "Has alcanzado el límite diario de análisis.";
    else if (res.status >= 500) msg = "Error del servidor. Inténtalo de nuevo en un momento.";
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

const api = {
  async uploadCv(file) {
    const body = new FormData();
    body.append("file", file);
    // Sin cabecera Content-Type: el navegador la genera con el boundary.
    return request("/cv", { method: "POST", body });
  },

  async confirmProfile(p) {
    return request("/cv/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: p }),
    });
  },

  async analyzeOffer(offer) {
    return request("/offer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ offer }),
    });
  },

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
// Paso 1a: subida
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
  $("upload-btn").textContent = "Extrayendo…";
  try {
    const data = await api.uploadCv(file);
    profile = normalizeProfile(data.profile);
    editing = null;
    $("upload-phase").hidden = true;
    $("review-phase").hidden = false;
    renderReview();
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    $("upload-btn").textContent = "Extraer mi perfil";
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
// Paso 1b: revisión (HITL): editar, añadir y quitar
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

async function onConfirm() {
  if (busy || editing !== null || totalEntries() === 0) return;
  clearMessage();
  setBusy(true);
  $("confirm-btn").textContent = "Guardando…";
  try {
    await api.confirmProfile(profile);
    showMessage("Perfil confirmado y guardado.");
    showStep(2);
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    $("confirm-btn").textContent = "Confirmar perfil";
    setBusy(false);
    renderReview();
  }
}

function onBackToUpload() {
  profile = null;
  editing = null;
  $("cv-file").value = "";
  fileCheck = { file: null, ok: false };
  $("file-error").hidden = true;
  $("review-phase").hidden = true;
  $("upload-phase").hidden = false;
  updateUploadButton();
  clearMessage();
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
  $("offer-btn").textContent = "Analizando…";
  try {
    const result = await api.analyzeOffer(offer);
    renderResult(result);
    showStep(3);
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    $("offer-btn").textContent = "Analizar oferta";
    setBusy(false);
  }
}

// ---------------------------------------------------------------------------
// Paso 3: resultado
// ---------------------------------------------------------------------------
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
  showStep(2);
}

// ---------------------------------------------------------------------------
// Borrar datos
// ---------------------------------------------------------------------------
async function onDelete() {
  if (busy) return;
  if (!window.confirm("Se borrarán tu perfil y tus datos. Esta acción no se puede deshacer. ¿Continuar?")) return;
  clearMessage();
  setBusy(true);
  try {
    await api.deleteProfile();
    onBackToUpload();
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
  $("confirm-btn").addEventListener("click", onConfirm);
  $("back-upload-btn").addEventListener("click", onBackToUpload);
  $("offer-text").addEventListener("input", updateOfferButton);
  $("offer-form").addEventListener("submit", onOfferSubmit);
  $("example-btn").addEventListener("click", onUseExample);
  $("another-btn").addEventListener("click", onAnotherOffer);
  $("delete-btn").addEventListener("click", onDelete);
  updateUploadButton();
  updateOfferButton();
  showStep(1);
}

init();