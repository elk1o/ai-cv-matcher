"use strict";

// Pon USE_MOCK = false cuando existan los endpoints en el backend.
const USE_MOCK = true;
const MAX_OFFER = 8000;
const MAX_FILE_BYTES = 5 * 1024 * 1024;
const ALLOWED_EXT = [".pdf", ".docx"];

const EXAMPLE_OFFER = `Senior Python Developer (Backend)

Buscamos un desarrollador/a backend con al menos 5 años de experiencia en Python.
Requisitos:
- Python y Django o FastAPI
- APIs REST y bases de datos PostgreSQL
- Experiencia con Docker y CI/CD
- Valorable: experiencia con LLMs, LangChain o LangGraph
- Valorable: Kubernetes
- Inglés B2 o superior`;

// Datos ficticios con la forma del contrato de los endpoints.
const MOCK_PROFILE = {
  experiencia: [
    { title: "Desarrollador backend · Empresa Ejemplo S.L.", detail: "2018-2022 · Python, Django, PostgreSQL" },
    { title: "Ingeniero de software · Compañía Demo", detail: "2022-actualidad · APIs REST, CI/CD" },
  ],
  formacion: [{ title: "Grado en Ingeniería Informática", detail: "Universidad Ejemplo" }],
  cursos: [{ title: "Curso de IA generativa", detail: "LangChain, RAG y agentes" }],
  skills: [
    { title: "Python", detail: "" },
    { title: "Django", detail: "" },
    { title: "PostgreSQL", detail: "" },
    { title: "Docker", detail: "" },
  ],
  idiomas: [{ title: "Inglés", detail: "B2" }],
};

const MOCK_RESULT = {
  score: 72,
  requirements: [
    { text: "Python 5+ años", status: "cumple", evidence: "Desarrollador backend en Empresa Ejemplo S.L. (2018-2022)." },
    { text: "Django o FastAPI", status: "cumple", evidence: "Django listado en habilidades y usado en Empresa Ejemplo." },
    { text: "PostgreSQL", status: "cumple", evidence: "PostgreSQL en habilidades y en la experiencia de 2018-2022." },
    { text: "Docker y CI/CD", status: "parcial", evidence: "CI/CD en Compañía Demo; Docker solo aparece en habilidades." },
    { text: "LLMs, LangChain o LangGraph", status: "parcial", evidence: "Curso de IA generativa con LangChain, RAG y agentes." },
    { text: "Kubernetes", status: "no_cumple", evidence: null },
    { text: "Inglés B2 o superior", status: "cumple", evidence: "Inglés B2 en idiomas." },
  ],
};

const SECTION_LABELS = {
  experiencia: "Experiencia",
  formacion: "Formación",
  cursos: "Cursos",
  skills: "Habilidades",
  idiomas: "Idiomas",
  logros: "Logros",
};

const STATUS_LABELS = { cumple: "Cumple", parcial: "Parcial", no_cumple: "No cumple" };

const state = { step: 1, profile: null, confirmed: false };

const $ = (id) => document.getElementById(id);
const steps = [1, 2, 3].map((n) => $(`step-${n}`));
const stepperItems = document.querySelectorAll(".stepper-item");
const statusEl = $("status");
const cvForm = $("cv-form");
const cvFile = $("cv-file");
const cvSubmit = $("cv-submit");
const profileReview = $("profile-review");
const profileSections = $("profile-sections");
const cvConfirm = $("cv-confirm");
const offerForm = $("offer-form");
const offerInput = $("offer");
const offerSubmit = $("offer-submit");
const counter = $("counter");
const scoreRing = $("score-ring");
const scoreValue = $("score-value");
const scoreSummary = $("score-summary");
const requirementsEl = $("requirements");

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

// ---- API (mock o real) ----

async function requestJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`El servidor respondió con el error ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

async function apiExtractProfile(file) {
  if (USE_MOCK) {
    await delay(900);
    return structuredClone(MOCK_PROFILE);
  }
  const body = new FormData();
  body.append("file", file);
  const data = await requestJson("/cv", { method: "POST", body });
  return data.profile;
}

async function apiConfirmProfile(profile) {
  if (USE_MOCK) {
    await delay(300);
    return;
  }
  await requestJson("/cv/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile }),
  });
}

async function apiAnalyze(offer) {
  if (USE_MOCK) {
    await delay(800);
    return MOCK_RESULT;
  }
  return requestJson("/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ offer }),
  });
}

async function apiDeleteData() {
  if (USE_MOCK) return;
  await requestJson("/profile", { method: "DELETE" });
}

// ---- Navegación entre pasos ----

function goTo(step) {
  if (step >= 2 && !state.confirmed) return;
  state.step = step;
  steps.forEach((section, index) => { section.hidden = index + 1 !== step; });
  stepperItems.forEach((item) => {
    const n = Number(item.dataset.step);
    item.classList.toggle("current", n === step);
    item.classList.toggle("done", n < step);
    if (n === step) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  });
  setStatus("");
  $(`title-${step}`).focus();
}

// ---- Paso 1: CV ----

function validateFile(file) {
  const name = file.name.toLowerCase();
  if (!ALLOWED_EXT.some((ext) => name.endsWith(ext))) return "Solo se admiten archivos PDF o DOCX.";
  if (file.size > MAX_FILE_BYTES) return "El archivo supera los 5 MB.";
  return null;
}

// Todo lo que viene del backend o del LLM se pinta con textContent, nunca con innerHTML.
function renderProfile() {
  profileSections.replaceChildren();
  let total = 0;

  Object.entries(SECTION_LABELS).forEach(([key, label]) => {
    const items = state.profile[key];
    if (!Array.isArray(items) || items.length === 0) return;
    total += items.length;

    const title = document.createElement("h4");
    title.textContent = label;
    const list = document.createElement("ul");
    list.className = "profile-list";

    items.forEach((entry, index) => {
      const li = document.createElement("li");
      li.className = "profile-item";

      const text = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = entry.title;
      text.append(strong);
      if (entry.detail) {
        const detail = document.createElement("span");
        detail.textContent = entry.detail;
        text.append(detail);
      }

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove-btn";
      remove.textContent = "Quitar";
      remove.setAttribute("aria-label", `Quitar: ${entry.title}`);
      remove.addEventListener("click", () => {
        items.splice(index, 1);
        renderProfile();
      });

      li.append(text, remove);
      list.append(li);
    });

    profileSections.append(title, list);
  });

  cvConfirm.disabled = total === 0;
}

function showReview() {
  cvForm.hidden = true;
  profileReview.hidden = false;
  renderProfile();
}

function showUpload() {
  state.profile = null;
  state.confirmed = false;
  cvForm.reset();
  cvForm.hidden = false;
  profileReview.hidden = true;
}

async function handleCvSubmit(event) {
  event.preventDefault();
  const file = cvFile.files[0];
  if (!file) {
    setStatus("Selecciona primero un archivo.", true);
    return;
  }
  const problem = validateFile(file);
  if (problem) {
    setStatus(problem, true);
    return;
  }

  cvSubmit.disabled = true;
  setStatus("Extrayendo tu perfil...");
  try {
    state.profile = await apiExtractProfile(file);
    state.confirmed = false;
    setStatus("");
    showReview();
  } catch (error) {
    setStatus(`No se pudo leer el CV: ${error.message}`, true);
  } finally {
    cvSubmit.disabled = false;
  }
}

async function handleConfirm() {
  cvConfirm.disabled = true;
  setStatus("Guardando tu perfil...");
  try {
    await apiConfirmProfile(state.profile);
    state.confirmed = true;
    goTo(2);
  } catch (error) {
    setStatus(`No se pudo guardar el perfil: ${error.message}`, true);
  } finally {
    cvConfirm.disabled = false;
  }
}

// ---- Paso 2: oferta ----

function updateCounter() {
  counter.textContent = `${offerInput.value.length} / ${MAX_OFFER}`;
}

async function handleOfferSubmit(event) {
  event.preventDefault();
  const offer = offerInput.value.trim();
  if (!offer) {
    setStatus("Pega primero el texto de una oferta.", true);
    return;
  }

  offerSubmit.disabled = true;
  setStatus("Analizando la oferta...");
  try {
    const data = await apiAnalyze(offer);
    renderResult(data);
    goTo(3);
  } catch (error) {
    setStatus(`No se pudo analizar la oferta: ${error.message}`, true);
  } finally {
    offerSubmit.disabled = false;
  }
}

// ---- Paso 3: resultado ----

function buildRequirementItem(requirement) {
  const item = document.createElement("li");
  item.className = "requirement";

  const head = document.createElement("div");
  head.className = "requirement-head";

  const status = STATUS_LABELS[requirement.status] ? requirement.status : "no_cumple";
  const badge = document.createElement("span");
  badge.className = `badge ${status}`;
  badge.textContent = STATUS_LABELS[status];

  const text = document.createElement("span");
  text.className = "requirement-text";
  text.textContent = requirement.text;

  head.append(badge, text);

  const evidence = document.createElement("p");
  evidence.className = "requirement-evidence";
  evidence.textContent = requirement.evidence || "Sin evidencia en tu perfil.";

  item.append(head, evidence);
  return item;
}

function renderResult(data) {
  if (!data || typeof data.score !== "number" || !Array.isArray(data.requirements)) {
    throw new Error("La respuesta del servidor no tiene el formato esperado");
  }
  const score = Math.max(0, Math.min(100, Math.round(data.score)));
  scoreValue.textContent = `${score}%`;
  scoreRing.style.setProperty("--score", String(score));

  const count = (status) => data.requirements.filter((r) => r.status === status).length;
  scoreSummary.textContent =
    `${count("cumple")} cumplidos · ${count("parcial")} parciales · ${count("no_cumple")} no cumplidos`;
  requirementsEl.replaceChildren(...data.requirements.map(buildRequirementItem));
}

// ---- Borrado de datos ----

async function handleDeleteData() {
  if (!window.confirm("¿Borrar tu perfil y todos tus datos? Esta acción no se puede deshacer.")) return;
  try {
    await apiDeleteData();
  } catch (error) {
    setStatus(`No se pudieron borrar los datos: ${error.message}`, true);
    return;
  }
  offerInput.value = "";
  updateCounter();
  showUpload();
  goTo(1);
  setStatus("Tus datos se han borrado.");
}

// ---- Eventos ----

cvForm.addEventListener("submit", handleCvSubmit);
cvConfirm.addEventListener("click", handleConfirm);
$("cv-reset").addEventListener("click", showUpload);
offerForm.addEventListener("submit", handleOfferSubmit);
offerInput.addEventListener("input", updateCounter);
$("example-btn").addEventListener("click", () => {
  offerInput.value = EXAMPLE_OFFER;
  updateCounter();
  offerInput.focus();
});
$("offer-back").addEventListener("click", () => {
  if (state.profile) showReview();
  goTo(1);
});
$("another-offer").addEventListener("click", () => goTo(2));
$("delete-data").addEventListener("click", handleDeleteData);

$("demo-banner").hidden = !USE_MOCK;
updateCounter();
goTo(1);
