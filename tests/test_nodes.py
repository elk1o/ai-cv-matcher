"""Tests of the extraction nodes (app/graph/nodes.py). The LLM is never called: the Google
client is replaced by a fake, so the real prompt template and the real error handling run."""
import pytest
from langchain_core.exceptions import ModelAPIError, ModelRateLimitError
from langchain_core.runnables import RunnableLambda

from app.graph import nodes
from app.graph.errors import (
    MODEL_UNAVAILABLE_MESSAGE,
    QUOTA_MESSAGE,
    ExtractionError,
    ModelQuotaError,
    ModelUnavailableError,
)
from app.graph.nodes import (
    MAX_REQUIREMENT_CHARS,
    MAX_REQUIREMENTS,
    _build_prompt,
    _ask_llm_to_extract,
    _EntryDraft,
    _OfferDraft,
    _ProfileDraft,
    _RequirementDraft,
    _to_profile,
    _to_requirements,
    extract_offer,
    extract_profile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_profile_draft(**sections) -> _ProfileDraft:
    base = {name: [] for name in _ProfileDraft.model_fields}
    base.update({k: [_EntryDraft(**e) for e in v] for k, v in sections.items()})
    return _ProfileDraft(**base)


def make_offer_draft(*items) -> _OfferDraft:
    return _OfferDraft(requirements=[_RequirementDraft(text=t, mandatory=m) for t, m in items])


class FakeGoogleModel:
    """Stands in for ChatGoogleGenerativeAI. `behaviour` receives what the chain sends to the
    model (the rendered prompt) and either returns the structured result or raises."""

    created_with: dict = {}
    behaviour = None

    def __init__(self, **kwargs):
        FakeGoogleModel.created_with = kwargs

    def with_structured_output(self, schema):
        return RunnableLambda(lambda prompt_value: FakeGoogleModel.behaviour(prompt_value))


@pytest.fixture
def fake_model(monkeypatch):
    """Installs the fake model. Usage: fake_model(lambda prompt_value: result_or_raise)."""
    monkeypatch.setenv("GEMINI_MODEL", "fake-model")
    monkeypatch.setattr("langchain_google_genai.ChatGoogleGenerativeAI", FakeGoogleModel)

    def install(behaviour):
        FakeGoogleModel.behaviour = behaviour

    return install


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
def test_prompt_wraps_the_text_in_text_tags():
    prompt = _build_prompt("sistema")
    assert prompt.input_variables == ["text_to_analyze"]
    human = prompt.invoke({"text_to_analyze": "hola"}).messages[1].content
    assert human == "<text>\nhola\n</text>"


# ---------------------------------------------------------------------------
# _to_profile
# ---------------------------------------------------------------------------
def test_to_profile_returns_profile():
    draft = make_profile_draft(skills=[{"title": "Python", "detail": ""}])
    assert _to_profile(draft).skills[0].title == "Python"


def test_to_profile_truncates_long_fields():
    draft = make_profile_draft(skills=[{"title": "T" * 500, "detail": "D" * 5000}])
    entry = _to_profile(draft).skills[0]
    assert len(entry.title) == 200
    assert len(entry.detail) == 2000


def test_to_profile_drops_entries_without_title():
    draft = make_profile_draft(skills=[{"title": "   ", "detail": "x"}, {"title": "SQL", "detail": ""}])
    assert [e.title for e in _to_profile(draft).skills] == ["SQL"]


def test_to_profile_caps_entries_per_section():
    draft = make_profile_draft(skills=[{"title": f"skill {i}", "detail": ""} for i in range(80)])
    assert len(_to_profile(draft).skills) == 50


@pytest.mark.parametrize("draft_class", [_ProfileDraft, _OfferDraft])
def test_draft_schemas_have_no_limits(draft_class):
    # Gemini rejects schemas with nested limits ("too many states"): the ones we send must have none.
    schema = str(draft_class.model_json_schema())
    for keyword in ("maxItems", "minItems", "maxLength", "minLength"):
        assert keyword not in schema


# ---------------------------------------------------------------------------
# _to_requirements
# ---------------------------------------------------------------------------
def test_to_requirements_trims_and_drops_empty():
    result = _to_requirements(make_offer_draft(("  Python  ", True), ("", True), ("   ", False), ("Inglés B2", False)))
    assert [(r.text, r.mandatory) for r in result] == [("Python", True), ("Inglés B2", False)]


def test_to_requirements_truncates_long_text():
    result = _to_requirements(make_offer_draft(("a" * 500, True)))
    assert len(result[0].text) == MAX_REQUIREMENT_CHARS


def test_to_requirements_caps_the_number_of_requirements():
    result = _to_requirements(make_offer_draft(*[(f"requisito {i}", True) for i in range(MAX_REQUIREMENTS + 10)]))
    assert len(result) == MAX_REQUIREMENTS


def test_to_requirements_removes_duplicates_ignoring_case():
    result = _to_requirements(make_offer_draft(("Docker", False), ("docker", False), ("DOCKER", False)))
    assert [r.text for r in result] == ["Docker"]


def test_to_requirements_keeps_mandatory_if_any_duplicate_is_mandatory():
    result = _to_requirements(make_offer_draft(("Docker", False), ("docker", True)))
    assert len(result) == 1 and result[0].mandatory is True


@pytest.mark.parametrize("items", [(), (("   ", True),)])
def test_to_requirements_rejects_an_empty_result(items):
    with pytest.raises(ExtractionError, match="requisitos"):
        _to_requirements(make_offer_draft(*items))


# ---------------------------------------------------------------------------
# _ask_llm_to_extract (fake Google model, real template and real error handling)
# ---------------------------------------------------------------------------
def test_ask_llm_returns_the_validated_schema(fake_model):
    fake_model(lambda _prompt: make_offer_draft(("Python", True)))
    result = _ask_llm_to_extract("sistema", "oferta", _OfferDraft, "los requisitos")
    assert isinstance(result, _OfferDraft)
    assert result.requirements[0].text == "Python"


def test_ask_llm_sends_the_text_inside_text_tags(fake_model):
    seen = {}

    def behaviour(prompt_value):
        seen["messages"] = prompt_value.messages
        return make_offer_draft(("Python", True))

    fake_model(behaviour)
    _ask_llm_to_extract("sistema", "texto de la oferta", _OfferDraft, "los requisitos")
    assert seen["messages"][0].content == "sistema"
    assert seen["messages"][1].content == "<text>\ntexto de la oferta\n</text>"


def test_ask_llm_uses_the_configured_retries_and_timeout(fake_model):
    fake_model(lambda _prompt: make_offer_draft(("Python", True)))
    _ask_llm_to_extract("sistema", "oferta", _OfferDraft, "los requisitos")
    assert FakeGoogleModel.created_with["model"] == "fake-model"
    assert FakeGoogleModel.created_with["max_retries"] == nodes.LLM_MAX_RETRIES
    assert FakeGoogleModel.created_with["timeout"] == nodes.LLM_TIMEOUT_SECONDS


def test_ask_llm_requires_the_model_name(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_MODEL"):
        _ask_llm_to_extract("sistema", "texto", _OfferDraft, "los requisitos")


def test_ask_llm_turns_rate_limit_into_quota_error(fake_model):
    error = ModelRateLimitError("429 RESOURCE_EXHAUSTED gemini-x quota")

    def behaviour(_prompt):
        raise error

    fake_model(behaviour)
    with pytest.raises(ModelQuotaError) as info:
        _ask_llm_to_extract("sistema", "texto", _OfferDraft, "los requisitos")
    assert str(info.value) == QUOTA_MESSAGE  # provider details are not leaked
    assert info.value.__cause__ is error


def test_ask_llm_turns_provider_503_into_unavailable_error(fake_model):
    error = ModelAPIError("503 UNAVAILABLE high demand")

    def behaviour(_prompt):
        raise error

    fake_model(behaviour)
    with pytest.raises(ModelUnavailableError) as info:
        _ask_llm_to_extract("sistema", "texto", _OfferDraft, "los requisitos")
    assert str(info.value) == MODEL_UNAVAILABLE_MESSAGE
    assert info.value.__cause__ is error


def test_ask_llm_wraps_any_other_error_in_extraction_error(fake_model):
    def behaviour(_prompt):
        raise TimeoutError("sin red")

    fake_model(behaviour)
    with pytest.raises(ExtractionError, match="los requisitos de la oferta"):
        _ask_llm_to_extract("sistema", "texto", _OfferDraft, "los requisitos de la oferta")


def test_ask_llm_rejects_an_empty_model_output(fake_model):
    fake_model(lambda _prompt: None)
    with pytest.raises(ExtractionError):
        _ask_llm_to_extract("sistema", "texto", _OfferDraft, "los requisitos")


def test_ask_llm_rejects_output_that_does_not_match_the_schema(fake_model):
    fake_model(lambda _prompt: {"requirements": "no es una lista"})
    with pytest.raises(ExtractionError):
        _ask_llm_to_extract("sistema", "texto", _OfferDraft, "los requisitos")


# ---------------------------------------------------------------------------
# The two nodes
# ---------------------------------------------------------------------------
def test_extract_profile_node_returns_profile_and_log(monkeypatch):
    seen = {}

    def fake_ask(system_prompt, text, schema, what):
        seen.update(system_prompt=system_prompt, text=text, schema=schema)
        return make_profile_draft(skills=[{"title": "Python", "detail": ""}])

    monkeypatch.setattr(nodes, "_ask_llm_to_extract", fake_ask)
    out = extract_profile({"cv_text": "mi cv"})
    assert seen["schema"] is _ProfileDraft
    assert seen["system_prompt"] == nodes.CV_EXTRACTION_SYSTEM_PROMPT
    assert seen["text"] == "mi cv"
    assert out["profile"].skills[0].title == "Python"
    assert len(out["log"]) == 1


def test_extract_profile_node_limits_the_cv_text_sent_to_the_model(monkeypatch):
    seen = {}

    def fake_ask(system_prompt, text, schema, what):
        seen["length"] = len(text)
        return make_profile_draft()

    monkeypatch.setattr(nodes, "_ask_llm_to_extract", fake_ask)
    extract_profile({"cv_text": "a" * (nodes.MAX_TEXT_CHARS + 1000)})
    assert seen["length"] == nodes.MAX_TEXT_CHARS


def test_extract_offer_node_returns_clean_requirements(monkeypatch):
    seen = {}

    def fake_ask(system_prompt, text, schema, what):
        seen.update(system_prompt=system_prompt, text=text, schema=schema)
        return make_offer_draft(("  Python  ", True), ("Docker", False))

    monkeypatch.setattr(nodes, "_ask_llm_to_extract", fake_ask)
    out = extract_offer({"offer_text": "la oferta"})
    assert seen["schema"] is _OfferDraft
    assert seen["system_prompt"] == nodes.OFFER_EXTRACTION_SYSTEM_PROMPT
    assert [(r.text, r.mandatory) for r in out["requirements"]] == [("Python", True), ("Docker", False)]
    assert len(out["log"]) == 1