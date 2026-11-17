# CV Matcher

[![Tests](https://github.com/elk1o/ai-cv-matcher/actions/workflows/tests.yml/badge.svg)](https://github.com/elk1o/ai-cv-matcher/actions/workflows/tests.yml)

CV Matcher is a web application that compares a job offer with your CV. You upload your CV, review the profile extracted from it, paste a job offer, and get a compatibility percentage together with a checklist of the requirements you meet, partially meet, or miss, each backed by evidence from your own profile.

The backend is built with FastAPI and is designed to run its matching logic on LangChain and LangGraph. The frontend is a dependency-free single page served by the same FastAPI app, so the whole project is a single deployment.

This project is in active development. The current version can already read a PDF or DOCX CV and extract a structured profile from it with Gemini, let the user confirm it, and delete it. The offer analysis endpoint is still a placeholder; see [Project status](#project-status) for what works today and what comes next.

## What is included

- A FastAPI application that serves a health check and the static frontend from a single URL.
- Pydantic schemas for the API contract in `app/schemas.py`, with input validation (length limits, score range, allowed statuses).
- **Real CV extraction** (`POST /cv`): the file type is detected from its content, the text is extracted from PDF (PyMuPDF) or DOCX (python-docx, including tables), and a Gemini model structures it into a profile through LangChain.
- **Profile confirmation and deletion** (`POST /cv/confirm`, `DELETE /profile`), backed by a temporary in-memory store.
- A placeholder router for the offer endpoint, which still returns a fixed response.
- A pytest suite in `tests/` (CV extraction, endpoints, and schemas) and a GitHub Actions workflow that runs it on every push and pull request. The tests never call the LLM.
- A three-step frontend written in plain HTML, CSS, and JavaScript, now connected to the backend:
  1. Upload a PDF or DOCX CV, then review the extracted profile and remove incorrect entries before confirming it.
  2. Paste the text of a job offer.
  3. Read the compatibility score and the requirement checklist with evidence.
- A defined API contract between the frontend and the backend, described below.

### CV extraction pipeline

`POST /cv` runs three steps, each with its own error type so the router can answer with the right HTTP status:

1. **Detect the file type by its magic bytes**, not by its name or extension. A PDF starts with `%PDF`; a DOCX is a ZIP that contains `word/document.xml`; old `.doc` files (OLE) are rejected with a clear message. Password-protected PDFs and corrupt files are rejected too.
2. **Extract the text.** PDF blocks are sorted so two-column CVs read in order; DOCX paragraphs and tables keep the document order, and merged table cells are not duplicated. The text is truncated to 30,000 characters. A DOCX whose uncompressed size exceeds 50 MB is rejected before opening it (zip bomb protection).
3. **Structure the text with the LLM.** The prompt lives in `app/prompts.py`. The model fills a limit-free draft schema (Gemini rejects schemas with many nested limits), and the limits of `Profile` are applied afterwards in code: long fields are truncated, entries without a title are dropped, and each section is capped at 50 entries.

The service layer (`app/services/cv_extraction.py`) does not import FastAPI. It raises its own exceptions and the router translates them:

| Exception | Meaning | HTTP status |
|---|---|---|
| `UnsupportedFileError` | Not a valid PDF/DOCX, `.doc`, corrupt, password-protected, or oversized DOCX | 415 |
| `EmptyCVError` | The file has no extractable text (for example, a scanned PDF) | 422 |
| `ModelQuotaError` | The shared Gemini quota or rate limit is exhausted | 503 |
| `ExtractionError` | The model failed or returned an invalid profile | 502 |

Uploads larger than 5 MB are rejected with `413`; the server reads at most 5 MB + 1 byte, so an oversized file is never fully loaded in memory.

## Design decisions

- **The score is not computed by the LLM.** The plan is for the model to extract structured requirements from the offer and to judge each one against the profile, citing the exact profile entry. The percentage is then calculated in code from weighted requirements, so it is reproducible and explainable.
- **The profile is stored as small entries, not raw text.** Each role, achievement, course, or skill is its own entry with metadata, which makes retrieval precise and citations exact.
- **The user confirms the extracted profile.** Extraction errors would silently contaminate every later match, so only confirmed entries are used.
- **Untrusted input is treated as untrusted.** Job offers and CV text can carry prompt injection. The CV text is sent between `<cv>` tags and the prompt tells the model to treat it as data, and the frontend renders every backend value with `textContent`, never `innerHTML`.
- **Privacy by design.** A CV is personal data: the original file is never stored, extraction does not save anything (the user must confirm first), error messages never include the CV text, and the frontend exposes a "Delete my data" action. The prompt also tells the model to leave out contact data (name, email, phone, address).
- **Limits are enforced in code, not trusted to the LLM.** Oversized fields are truncated instead of rejected, because a 201-character title does not justify an error.
- **Quota errors are not the user's fault.** When the shared Gemini quota is exhausted the API answers `503`, not `429`, with a generic message; the provider's details are only logged.

## Technology

Python, FastAPI, Uvicorn, Pydantic, `python-multipart` for file uploads, PyMuPDF and python-docx to read CVs, LangChain with `langchain-google-genai` (Gemini) for the extraction, pytest and HTTPX for tests, GitHub Actions for continuous integration, and vanilla HTML, CSS, and JavaScript for the frontend. LangGraph and a vector store are planned for the matching logic. The pinned dependency versions are listed in [requirements.txt](requirements.txt).

## Repository structure

The offer router is still a placeholder and returns fixed responses.

```text
.
├── .github/
│   └── workflows/
│       └── tests.yml      # runs pytest on every push and pull request
├── app/
│   ├── __init__.py
│   ├── main.py            # app creation, routers, static files mounted last
│   ├── schemas.py         # Pydantic models for the API contract
│   ├── prompts.py         # system prompt for the CV extraction
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── cv.py          # POST /cv and POST /cv/confirm
│   │   ├── offer.py       # /offer (placeholder responses)
│   │   └── profile.py     # DELETE /profile
│   └── services/
│       ├── __init__.py
│       ├── cv_extraction.py  # file detection, text extraction, LLM structuring
│       └── profile_store.py  # temporary in-memory store of the confirmed profile
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── tests/
│   ├── test_cv.py         # extraction, /cv, /cv/confirm and /profile
│   └── test_schemas.py    # schema validation
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

CV extraction calls Gemini, so the backend needs two environment variables. Put them in a `.env` file at the repository root (it is loaded at startup and ignored by git) or export them in your shell:

```text
GEMINI_MODEL=<name of the Gemini model to use>
GOOGLE_API_KEY=<your Google AI API key>
```

If `GEMINI_MODEL` is missing, `POST /cv` fails when it reaches the LLM step. The tests do not need either variable. Do not commit `.env` or any credentials.

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

The frontend talks to the real backend: the former demo mode with fictional data (`USE_MOCK`) is gone. Until offer matching is implemented, step 3 (`POST /offer`) only receives the placeholder response.

## Running tests

Install the dependencies as described in [Getting started](#getting-started), then run from the repository root:

```bash
python -m pytest tests -v
```

Use `-s` as well if you want to see the output printed by the tests:

```bash
python -m pytest tests -vs
```

The CV tests build PDF and DOCX files in memory and replace the LLM with a fake chain (using pytest's `monkeypatch`), so they are deterministic, need no network or API key, and consume no quota. They cover file detection, text extraction (tables, merged cells, document order, truncation, zip bombs), the limits applied to the model output, error wrapping, and every status code of the CV endpoints.

### Continuous integration

The workflow in `.github/workflows/tests.yml` runs the same command on every push to `master` and on every pull request. It installs the dependencies from `requirements.txt` on Python 3.12 and has read-only access to the repository. It only reports the result of the tests; it does not deploy anything. Deployment is handled separately by Render (see [Deployment](#deployment)).

## API contract

This is the contract defined by the schemas in `app/schemas.py` (`ProfileResponse`, `ProfileConfirmRequest`, `OfferRequest`, `OfferResponse`). `POST /cv`, `POST /cv/confirm`, and `DELETE /profile` are implemented; `POST /offer` still returns a fixed response.

| Action | Endpoint | Request | Response |
|---|---|---|---|
| Upload a CV | `POST /cv` | `multipart/form-data`, field `file` | `{"profile": {...}}` |
| Confirm the profile | `POST /cv/confirm` | `{"profile": {...}}` | `204 No Content` |
| Analyze an offer | `POST /offer` | `{"offer": "..."}` | `{"score": 72, "requirements": [...]}` |
| Delete the user's data | `DELETE /profile` | none | `204 No Content` |

A profile has the sections `experience`, `education`, `courses`, `skills`, `languages`, and `achievements`, each a list of up to 50 entries. An entry is `{"title": "...", "detail": "..."}`: `title` is required (1 to 200 characters), `detail` is optional (up to 2000), and surrounding whitespace is stripped.

The offer text must be between 10 and 8000 characters. The response `score` is an integer from 0 to 100. Each requirement is `{"text": "...", "status": "...", "evidence": "..."}`, where `status` is `OK`, `Partial`, or `KO`, and `evidence` is optional and `null` when the profile has nothing to support the requirement.

Error responses of `POST /cv` (the `detail` message is in Spanish, since the user sees it):

| Status | When |
|---|---|
| `413` | The file is larger than 5 MB |
| `415` | The file is not a valid PDF or DOCX (also `.doc`, corrupt, password-protected) |
| `422` | The file has no extractable text, or the `file` field is missing |
| `502` | The model failed or returned an invalid profile |
| `503` | The shared model quota is exhausted |

`POST /cv/confirm` answers `422` if any entry is invalid (for example, an empty title) and stores nothing. Confirmed profiles are kept in memory under a single anonymous user, so they are lost on restart.

Pending: the placeholder offer router still exposes `GET /offer`, which is not part of the contract.

## Deployment

The target platform is the Render free plan, deploying directly from GitHub:

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Free web services sleep after a period of inactivity, so the first request can take around a minute. Free instance disks are ephemeral, so persistent data will need an external database.

## Project status

The project is under development.

Done:

- FastAPI application serving the health check and the frontend.
- Pydantic schemas for the API contract, with validation.
- Real CV extraction: server-side validation of size and file contents, PDF and DOCX text extraction, and structuring with Gemini.
- `POST /cv/confirm` and `DELETE /profile`, with a temporary in-memory store.
- Frontend aligned with the contract (route and `OK`/`Partial`/`KO` statuses) and connected to the backend.
- pytest suite (81 tests) and a GitHub Actions workflow that runs it on every push and pull request.

Next:

1. Implement real offer matching: requirement extraction, evidence retrieval, and a score calculated in code.
2. Add persistence, per-user data isolation, invitation codes, and a daily usage quota.

## Author

elk1o.dev@gmail.com

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.