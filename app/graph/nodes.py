"""
Nodes of the matching graph. Each one is a function: state in, partial state out.
"""
import os
import logging
from app.graph.state import MatchState
from app.schemas import Profile, Requirement
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.exceptions import ModelRateLimitError, ModelAPIError
from app.graph.errors import ExtractionError, ModelQuotaError, QUOTA_MESSAGE, \
ModelUnavailableError, MODEL_UNAVAILABLE_MESSAGE
from pydantic import BaseModel
from app.prompts import CV_EXTRACTION_SYSTEM_PROMPT, OFFER_EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 30_000  # max CV text length sent to the LLM
MAX_TITLE_CHARS = 200
MAX_DETAIL_CHARS = 2000
MAX_ENTRIES_PER_SECTION = 50

LLM_MAX_RETRIES = 2
LLM_TIMEOUT_SECONDS = 90

MAX_REQUIREMENTS = 30
MAX_REQUIREMENT_CHARS = 300

class _RequirementDraft(BaseModel):
    """Requirement as returned by the LLM. No limits (Gemini rejects nested limits)."""
    text: str
    mandatory: bool

class _OfferDraft(BaseModel):
    """Schema sent to the LLM for the offer. The limits are applied in _to_requirements."""
    requirements: list[_RequirementDraft]

class _EntryDraft(BaseModel):
    """Entry as returned by the LLM. No limits: Gemini rejects schemas with many nested
    limits ("too many states for serving")."""
    title: str
    detail: str

class _ProfileDraft(BaseModel):
    """Schema sent to the LLM. The limits are applied afterwards, in _to_profile."""
    experience: list[_EntryDraft]
    education: list[_EntryDraft]
    courses: list[_EntryDraft]
    skills: list[_EntryDraft]
    languages: list[_EntryDraft]
    achievements: list[_EntryDraft]

def _clean_entries(entries: list[_EntryDraft]) -> list[dict]:
    cleaned = []
    for entry in entries:
        title = entry.title.strip()[:MAX_TITLE_CHARS].strip()
        if not title:  # an entry without a title is useless
            continue
        cleaned.append({"title": title, "detail": entry.detail.strip()[:MAX_DETAIL_CHARS]})
    return cleaned[:MAX_ENTRIES_PER_SECTION]

def _to_profile(draft: _ProfileDraft) -> Profile:
    """Apply the limits to the LLM draft and validate it as a Profile.

    Fields are truncated instead of rejected: a 201-character title does not justify a 502.
    """
    data = {name: _clean_entries(getattr(draft, name)) for name in _ProfileDraft.model_fields}
    return Profile.model_validate(data)

def _to_requirements(draft: _OfferDraft) -> list[Requirement]:
    """Clean the LLM draft: trim, truncate, drop empty and duplicated requirements."""
    unique: dict[str, Requirement] = {}
    for item in draft.requirements:
        text = item.text.strip()[:MAX_REQUIREMENT_CHARS].strip()
        if not text:  # a requirement without text is useless
            continue
        key = text.casefold()  # same requirement with different capitalization
        if key in unique:
            if item.mandatory:  # if it appears as mandatory anywhere, keep it mandatory
                unique[key].mandatory = True
            continue
        unique[key] = Requirement(text=text, mandatory=item.mandatory)

    requirements = list(unique.values())[:MAX_REQUIREMENTS]
    if not requirements:
        raise ExtractionError("No se han encontrado requisitos en la oferta. Revisa el texto.")
    return requirements

def _build_prompt(system_prompt: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", "<text>\n{text_to_analyze}\n</text>")]
    )

def _ask_llm_to_extract(system_prompt, text, schema, what):
    # Lazy import: faster startup, and the tests do not need the Google SDK.
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = os.environ.get("GEMINI_MODEL")
    if not model:
        raise RuntimeError("Falta la variable de entorno GEMINI_MODEL.")

    prompt = _build_prompt(system_prompt)
    llm = ChatGoogleGenerativeAI(model=model, max_retries=LLM_MAX_RETRIES, timeout=LLM_TIMEOUT_SECONDS)

    chain = prompt | llm.with_structured_output(schema)
    try:
        result = chain.invoke({"text_to_analyze": text})
        return schema.model_validate(result)
    except ModelRateLimitError as exc:
        logger.warning("Model quota exceeded: %s", type(exc).__name__)
        raise ModelQuotaError(QUOTA_MESSAGE) from exc
    except ModelAPIError as exc:
        logger.warning("Model unavailable: %s", type(exc).__name__)
        raise ModelUnavailableError(MODEL_UNAVAILABLE_MESSAGE) from exc
    except Exception as exc:
        logger.exception("Extraction of %s failed: %s", what, type(exc).__name__)
        raise ExtractionError(f"No se pudo extraer {what}. Inténtalo de nuevo.") from exc


def extract_profile(state: MatchState) -> MatchState:
    """ Get cv text and extract structured info with LLM """
    draft = _ask_llm_to_extract(
        CV_EXTRACTION_SYSTEM_PROMPT, state["cv_text"][:MAX_TEXT_CHARS], _ProfileDraft, "el perfil del CV"
    )
    return {
        "profile": _to_profile(draft),
        "log": ["Estructurado el texto del CV"]
    }    

def extract_offer(state: MatchState) -> MatchState:
    """ Get offer text and extract the requirements with LLM """
    draft = _ask_llm_to_extract(
        OFFER_EXTRACTION_SYSTEM_PROMPT, state["offer_text"], _OfferDraft, "los requisitos de la oferta"
    )
    return {
        "requirements": _to_requirements(draft),
        "log": ["Estructurado el texto de la oferta"]
    }
        
def review_human(state: MatchState) -> MatchState:
    """Pause the graph so the user can edit profile (HITL).

    Keep this node alone: when the graph resumes, the node runs again from its first line,
    so an LLM call inside it would be repeated.
    """
    raise NotImplementedError


def evaluate(state: MatchState) -> MatchState:
    """Compare every requirement with the profile. Writes `evaluations` and `attempts`."""
    raise NotImplementedError


def verify_evidence(state: MatchState) -> MatchState:
    """Check that each evidence really appears in the profile (code, no LLM)."""
    raise NotImplementedError


def compute_score(state: MatchState) -> MatchState:
    """Score computed in code (never by the LLM). Writes `result`."""
    raise NotImplementedError