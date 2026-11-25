# CV Matcher

[![Tests](https://github.com/elk1o/ai-cv-matcher/actions/workflows/tests.yml/badge.svg)](https://github.com/elk1o/ai-cv-matcher/actions/workflows/tests.yml)

CV Matcher is a web application that compares a job offer with your CV. You upload your CV, paste a job offer, review the profile extracted from your CV, and get a compatibility percentage together with a checklist of the requirements you meet, partially meet, or miss, each backed by evidence from your own profile.

The backend is built with FastAPI, LangChain, and LangGraph, with Gemini as the model. The frontend is a dependency-free single page served by the same FastAPI app, so the whole project is a single deployment.

This project is in active development. The current version reads a PDF or DOCX CV, stores the text of the CV and of the offer, and runs the first part of a multi-agent LangGraph graph that extracts a structured profile from the CV and the requirements from the offer in parallel. The human review step and the matching itself are not implemented yet; see [Project status](#project-status) for what works today and what comes next.

## What is included

- A FastAPI application that serves a health check and the static frontend from a single URL.
- Pydantic schemas for the API contract in `app/schemas.py`, with input validation (length limits, score range, allowed statuses).
- **Step 1, CV upload** (`POST /cv`): the file type is detected from its content, the text is extracted locally from PDF (PyMuPDF) or DOCX (python-docx, including tables) and stored in memory. **No LLM is called in this step.**
- **Step 2, offer upload** (`POST /offer`): the pasted text is validated, stripped, and stored in memory. **No LLM is called in this step either.**
- **Step 3, analysis** (`POST /match`): a LangGraph graph runs two LLM extractions in parallel (the profile from the CV, the requirements from the offer) and returns the profile so the user can review it.
- **Data deletion** (`DELETE /profile`): removes the stored profile and the raw CV and offer texts.
- Two extraction prompts in `app/prompts.py`, structured in five sections (role, context, exact task, constraints with guardrails, output format).
- A pytest suite in `tests/` (CV files, extraction nodes, graph wiring, endpoints, errors, prompts, and schemas) and a GitHub Actions workflow that runs it on every push and pull request. The tests never call the LLM.
- A three-step frontend written in plain HTML, CSS, and JavaScript, connected to the backend:
  1. Upload a PDF or DOCX CV (the interface shows how many characters were loaded).
  2. Paste the text of a job offer, or use an example offer (also shows the number of characters loaded).
  3. Start the analysis, review and edit the extracted profile, and read the result. Buttons are disabled as soon as they are pressed, and a loading indicator is shown while the model works.
- A defined API contract between the frontend and the backend, described below.

### How the three steps fit together

```text
Step 1  POST /cv      validate file, extract text locally, store it       (no LLM)
Step 2  POST /offer   validate text, store it                             (no LLM)
Step 3  POST /match   LangGraph graph
                      ├── extract_profile  (CV text   -> Profile)   ┐ in parallel,
                      └── extract_offer    (offer text -> requirements) ┘ two LLM calls
                      -> returns {thread_id, profile} for manual review
        planned:      review_human (interrupt) -> evaluate -> verify_evidence -> compute_score
```

Only the CV profile is reviewed by the user; the requirements extracted from the offer are accepted as the model returned them.

### CV file handling

`POST /cv` runs two steps, each with its own error type so the router can answer with the right HTTP status:

1. **Detect the file type by its magic bytes**, not by its name or extension. A PDF starts with `%PDF`; a DOCX is a ZIP that contains `word/document.xml`; old `.doc` files (OLE) are rejected with a clear message. Password-protected PDFs and corrupt files are rejected too.
2. **Extract the text.** PDF blocks are sorted so two-column CVs read in order; DOCX paragraphs and tables keep the document order, and merged table cells are not duplicated. A DOCX whose uncompressed size exceeds 50 MB is rejected before opening it (zip bomb protection).

The file service (`app/services/cv_extraction.py`) does not import FastAPI. It raises its own exceptions and the router translates them:

| Exception | Meaning | HTTP status |
|---|---|---|
| `UnsupportedFileError` | Not a valid PDF/DOCX, `.doc`, corrupt, password-protected, or oversized DOCX | 415 |
| `EmptyCVError` | The file has no extractable text (for example, a scanned PDF) | 422 |

Uploads larger than 5 MB are rejected with `413`; the server reads at most 5 MB + 1 byte, so an oversized file is never fully loaded in memory.

### The analysis graph

The graph lives in `app/graph/`:

| File | Content |
|---|---|
| `state.py` | `MatchState`, the shared state. `log` uses a reducer so parallel nodes can both write to it. |
| `nodes.py` | The nodes, the draft schemas sent to the model, the cleaning functions, and the LLM call. |
| `builder.py` | Builds the graph, runs it, and returns the response. |
| `errors.py` | Domain exceptions and their user-facing messages (in Spanish). |

How the extraction nodes work:

- **One LLM helper for both nodes.** `_ask_llm_to_extract(system_prompt, text, schema, what)` builds the prompt (the text is sent between `<text>` and `</text>`), calls Gemini with structured output, and translates provider errors into domain errors.
- **Limit-free draft schemas.** Gemini rejects schemas with many nested limits ("too many states for serving"), so the model fills `_ProfileDraft` and `_OfferDraft` without limits and the limits are applied afterwards in code (`_to_profile`, `_to_requirements`).
- **Cleaning in code.** Long fields are truncated, entries without a title are dropped, each profile section is capped at 50 entries, and requirements are trimmed, deduplicated ignoring capitalization (a duplicate that is mandatory anywhere stays mandatory), and capped at 30. If no requirement is found, the node raises an error instead of continuing with an empty list.
- **At most 30,000 characters of the CV** are sent to the model.
- **Retries and timeout** are constants in `nodes.py` (`LLM_MAX_RETRIES`, `LLM_TIMEOUT_SECONDS`).

Errors raised inside a node propagate unchanged out of the graph, and the router translates them:

| Exception | Meaning | HTTP status |
|---|---|---|
| `ModelQuotaError` | The shared Gemini quota or rate limit is exhausted | 503 |
| `ModelUnavailableError` | Gemini is overloaded or returned a server error | 503 |
| `ExtractionError` | The model failed, returned an invalid result, or the offer has no requirements | 502 |

The extraction prompts ask for the output in Spanish: if the CV or the offer is written in another language, the profile and the requirements are translated, except proper names, technologies, and tools.

## Design decisions

- **The score is not computed by the LLM.** The plan is for the model to judge each requirement against the profile, citing the exact profile entry, and for the percentage to be calculated in code (OK = 1, Partial = 0.5, KO = 0), so it is reproducible and explainable.
- **Steps 1 and 2 do not use AI.** Uploading only validates and extracts text; all LLM work happens in step 3, inside one graph, so quota is only spent when the user starts the analysis.
- **The user reviews the extracted profile.** Extraction errors would silently contaminate the match, so the graph is designed to pause and let the user edit the profile before evaluating. The offer is not reviewed.
- **Untrusted input is treated as untrusted.** Job offers and CV text can carry prompt injection. The text is sent between `<text>` tags, the system prompt tells the model to treat it as data and to ignore instructions inside it, and the frontend renders every backend value with `textContent`, never `innerHTML`.
- **Privacy by design.** A CV is personal data: the original file is never stored, the raw CV and offer texts live only in memory and are removed by `DELETE /profile`, error messages never include the CV text, and the frontend exposes a "Delete my data" action. The prompt also tells the model to leave out contact data (name, email, phone, address). Note that the CV text is sent to Google Gemini for step 3, and the interface says so.
- **Limits are enforced in code, not trusted to the LLM.** Oversized fields are truncated instead of rejected, because a 201-character title does not justify an error.
- **Quota and overload errors are not the user's fault.** When the shared Gemini quota is exhausted or the model is overloaded, the API answers `503`, not `429`, with a generic message; the provider's details are never sent to the client.
- **Services do not import FastAPI.** They raise domain exceptions; the routers translate them into HTTP responses.

## Technology

Python, FastAPI, Uvicorn, Pydantic, `python-multipart` for file uploads, PyMuPDF and python-docx to read CVs, LangChain with `langchain-google-genai` (Gemini) and LangGraph for the multi-agent graph, pytest and HTTPX for tests, GitHub Actions for continuous integration, and vanilla HTML, CSS, and JavaScript for the frontend. A vector store is planned for a later phase. The pinned dependency versions are listed in [requirements.txt](requirements.txt).

## Repository structure

```text
.
├── .github/
│   └── workflows/
│       └── tests.yml          # runs pytest on every push and pull request
├── app/
│   ├── __init__.py
│   ├── main.py                # app creation, routers, static files mounted last
│   ├── schemas.py             # Pydantic models for the API contract
│   ├── prompts.py             # system prompts for the CV and offer extraction
│   ├── graph/
│   │   ├── state.py           # MatchState (shared state of the graph)
│   │   ├── nodes.py           # extraction nodes, cleaning functions, LLM call
│   │   ├── builder.py         # builds and runs the graph
│   │   └── errors.py          # domain exceptions and user messages
│   ├── routers/
│   │   ├── cv.py              # POST /cv
│   │   ├── offer.py           # POST /offer
│   │   ├── match.py           # POST /match
│   │   └── profile.py         # DELETE /profile
│   └── services/
│       ├── cv_extraction.py   # file detection and text extraction (no LLM)
│       ├── document_store.py  # in-memory store of the raw CV and offer texts
│       └── profile_store.py   # in-memory store of the profile
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── tests/
│   ├── test_cv.py             # file detection, text extraction, /cv and /profile
│   ├── test_offer.py          # /offer
│   ├── test_nodes.py          # extraction nodes, cleaning, LLM error handling
│   ├── test_graph.py          # graph wiring
│   ├── test_match.py          # POST /match and its HTTP error codes
│   ├── test_errors.py         # domain exceptions
│   ├── test_prompts.py        # sanity checks of the system prompts
│   └── test_schemas.py        # schema validation
├── .gitignore
├── LICENSE
├── requirements.txt
└── README.md
```

## Getting started

Use Python 3.10 or newer, then create and activate a virtual environment from the repository root and install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

The analysis step calls Gemini, so the backend needs two environment variables. Put them in a `.env` file at the repository root (it is loaded at startup and ignored by git) or export them in your shell:

```text
GEMINI_MODEL=<name of the Gemini model to use>
GOOGLE_API_KEY=<your Google AI API key>
```

If `GEMINI_MODEL` is missing, `POST /match` fails when it reaches the LLM. Steps 1 and 2 do not need either variable, and neither do the tests. Do not commit `.env` or any credentials.

## Running the application

Run the server from the repository root:

```bash
uvicorn app.main:app --reload
```

Then open:

- `http://127.0.0.1:8000/` for the three-step interface.
- `http://127.0.0.1:8000/health` for the health check.
- `http://127.0.0.1:8000/docs` for the interactive API documentation generated by FastAPI.

The static files are mounted last in `app/main.py` on purpose: a mount on `/` would otherwise capture every route registered after it.

Until the second half of the graph is implemented, the frontend can start the analysis and show the extracted profile, but the review confirmation and the result (step 3 resume) do not have a backend endpoint yet.

## Running tests

Install the dependencies as described in [Getting started](#getting-started), then run from the repository root:

```bash
python -m pytest tests -v
```

Use `-s` as well if you want to see the output printed by the tests:

```bash
python -m pytest tests -vs
```

The tests are deterministic, need no network or API key, and consume no quota:

- CV tests build PDF and DOCX files in memory.
- Node tests replace `ChatGoogleGenerativeAI` with a fake model, so the real prompt template and the real error handling run. They cover the cleaning functions, the retries and timeout passed to the client, the translation of a rate limit (429) into `ModelQuotaError`, of a provider error into `ModelUnavailableError`, and of anything else into `ExtractionError`.
- Graph tests replace the nodes with fakes to check the wiring, that both branches run with their own text, and that errors reach the router unchanged.
- Router tests replace the graph and check the preconditions (`409` when a step is missing) and every error code.
- Prompt tests catch stray curly braces (which LangChain would read as template variables) and leftover tags that contradict the human message.
- Step 1 and step 2 tests check that the LLM is never called.

### Continuous integration

The workflow in `.github/workflows/tests.yml` runs the same command on every push to `master` and on every pull request. It installs the dependencies from `requirements.txt` on Python 3.12 and has read-only access to the repository. It only reports the result of the tests; it does not deploy anything. Deployment is handled separately by Render (see [Deployment](#deployment)).

## API contract

This is the contract defined by the schemas in `app/schemas.py`.

| Action | Endpoint | Request | Response |
|---|---|---|---|
| Upload a CV | `POST /cv` | `multipart/form-data`, field `file` | `{"characters": 1234}` |
| Upload an offer | `POST /offer` | `{"offer": "..."}` | `{"characters": 1234}` |
| Start the analysis | `POST /match` | none (uses the stored CV and offer) | `{"thread_id": "...", "profile": {...}}` |
| Delete the user's data | `DELETE /profile` | none | `204 No Content` |
| Resume the analysis (planned) | `POST /match/{thread_id}/resume` | `{"profile": {...}}` | `{"score": 72, "requirements": [...]}` |

A profile has the sections `experience`, `education`, `courses`, `skills`, `languages`, and `achievements`, each a list of up to 50 entries. An entry is `{"title": "...", "detail": "..."}`: `title` is required (1 to 200 characters), `detail` is optional (up to 2000), and surrounding whitespace is stripped.

The offer text must be between 10 and 8000 characters after stripping. The planned result `score` is an integer from 0 to 100. Each requirement of the result is `{"text": "...", "status": "...", "evidence": "..."}`, where `status` is `OK`, `Partial`, or `KO`, and `evidence` is optional and `null` when the profile has nothing to support the requirement.

Error responses (the `detail` message is in Spanish, since the user sees it):

| Endpoint | Status | When |
|---|---|---|
| `POST /cv` | `413` | The file is larger than 5 MB |
| `POST /cv` | `415` | The file is not a valid PDF or DOCX (also `.doc`, corrupt, password-protected) |
| `POST /cv` | `422` | The file has no extractable text, or the `file` field is missing |
| `POST /offer` | `422` | The offer is shorter than 10 characters after stripping, or longer than 8000 |
| `POST /match` | `409` | The CV or the offer has not been uploaded yet |
| `POST /match` | `502` | The model failed, returned an invalid result, or the offer has no requirements |
| `POST /match` | `503` | The shared model quota is exhausted, or the model is overloaded |

Texts and profiles are kept in memory under a single anonymous user, so they are lost on restart.

## Deployment

The target platform is the Render free plan, deploying directly from GitHub:

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment variables (Environment tab of the service): `GOOGLE_API_KEY` and `GEMINI_MODEL`.

Free web services sleep after a period of inactivity, so the first request can take around a minute. Free instance disks are ephemeral, so persistent data will need an external database.

## Project status

The project is under development.

Done:

- FastAPI application serving the health check and the frontend.
- Pydantic schemas for the API contract, with validation.
- Step 1 and step 2: server-side validation, local text extraction, and in-memory storage, without any LLM call.
- LangGraph graph with the two extraction nodes running in parallel, error handling for quota and overload, and `POST /match` returning the profile for review.
- Extraction prompts structured in five sections, with prompt-injection guardrails and Spanish output.
- Frontend with the three steps, character counters, loading indicators, disabled buttons while a request is running, and the profile review screen.
- pytest suite (130 tests) and a GitHub Actions workflow that runs it on every push and pull request.

Next:

1. Finish the graph: `review_human` with `interrupt()` and a checkpointer, `evaluate`, `verify_evidence` (with a retry loop), and `compute_score`, plus the `POST /match/{thread_id}/resume` endpoint and a real `thread_id`.
2. Add persistence (an optional, consented "save my profile"), per-user data isolation, invitation codes, and a daily usage quota.

## Author

elk1o.dev@gmail.com

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.