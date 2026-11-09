"use strict";

// ---------------------------------------------------------------------------
// Configuración
// ---------------------------------------------------------------------------
// true  -> datos ficticios, no se llama al backend.
// false -> llama a los endpoints reales (mismo origen).
const USE_MOCK = true;

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
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function request(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let msg = `Error ${res.status}.`;
    if (res.status === 401) msg = "Código de acceso inválido.";
    else if (res.status === 422) msg = "Los datos enviados no son válidos. Revisa los límites de longitud.";
    else if (res.status === 429) msg = "Has alcanzado el límite diario de análisis.";
    else if (res.status >= 500) msg = "Error del servidor. Inténtalo de nuevo en un momento.";
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

const MOCK_PROFILE = {
  experience: [
    { title: "Desarrollador backend — Empresa Ejemplo", detail: "2020-2024. APIs REST con Python y bases de datos relacionales." },
    { title: "Desarrollador junior — Estudio Demo", detail: "2018-2020. Mantenimiento de aplicaciones web." },
  ],
  education: [{ title: "Grado en Informática — Universidad Ficticia", detail: "" }],
  courses: [{ title: "Curso de bases de datos", detail: "40 horas" }],
  skills: [{ title: "Python" }, { title: "SQL" }, { title: "Git" }].map((s) => ({ detail: "", ...s })),
  languages: [{ title: "Inglés", detail: "B2" }],
  achievements: [],
};

const api = {
  async uploadCv(file) {
    if (USE_MOCK) {
      await sleep(700);
      return { profile: structuredClone(MOCK_PROFILE) };
    }
    const body = new FormData();
    body.append("file", file);
    // Sin cabecera Content-Type: el navegador la genera con el boundary.
    return request("/cv", { method: "POST", body });
  },

  async confirmProfile(p) {
    if (USE_MOCK) {
      await sleep(300);
      return null;
    }
    return request("/cv/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: p }),
    });
  },

  async analyzeOffer(offer) {
    if (USE_MOCK) {
      await sleep(900);
      return {
        score: 67,
        requirements: [
          { text: "Python", status: "OK", evidence: "Desarrollador backend — Empresa Ejemplo: APIs REST con Python" },
          { text: "Bases de datos SQL", status: "OK", evidence: "Skill: SQL" },
          { text: "Experiencia con Docker", status: "Partial", evidence: "Mencionas despliegues, pero no Docker de forma explícita" },
          { text: "AWS", status: "KO", evidence: null },
        ],
      };
    }
    return request("/offer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ offer }),
    });
  },

  async deleteProfile() {
    if (USE_MOCK) {
      await sleep(300);
      return null;
    }
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
function validateFile(file) {
  if (!file) return "Selecciona un archivo.";
  const name = file.name.toLowerCase();
  if (!name.endsWith(".pdf") && !name.endsWith(".docx")) return "Solo se admiten archivos PDF o DOCX.";
  if (file.size > LIMITS.fileBytes) return "El archivo supera los 5 MB.";
  if (file.size === 0) return "El archivo está vacío.";
  return null;
}

function updateUploadButton() {
  const file = $("cv-file").files[0];
  $("upload-btn").disabled = busy || !file || !$("consent").checked || validateFile(file) !== null;
}

function onFileChange() {
  const file = $("cv-file").files[0];
  const error = file ? validateFile(file) : null;
  const el = $("file-error");
  el.textContent = error || "";
  el.hidden = !error;
  updateUploadButton();
}

async function onUploadSubmit(event) {
  event.preventDefault();
  const file = $("cv-file").files[0];
  if (busy || validateFile(file) !== null || !$("consent").checked) return;

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
  $("demo-banner").hidden = !USE_MOCK;
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