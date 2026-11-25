"""Sanity checks of the system prompts. They catch edits that would break LangChain
(stray curly braces become template variables) or contradict the human message."""
import pytest

from app.graph.nodes import _build_prompt
from app.prompts import CV_EXTRACTION_SYSTEM_PROMPT, OFFER_EXTRACTION_SYSTEM_PROMPT

PROMPTS = [CV_EXTRACTION_SYSTEM_PROMPT, OFFER_EXTRACTION_SYSTEM_PROMPT]


@pytest.mark.parametrize("system_prompt", PROMPTS)
def test_prompt_has_no_stray_template_variables(system_prompt):
    # The only variable allowed in the whole template is the one of the human message.
    assert _build_prompt(system_prompt).input_variables == ["text_to_analyze"]


@pytest.mark.parametrize("system_prompt", PROMPTS)
def test_prompt_talks_about_the_tags_the_text_is_sent_in(system_prompt):
    assert "<text>" in system_prompt and "</text>" in system_prompt


@pytest.mark.parametrize("system_prompt", PROMPTS)
def test_prompt_does_not_mention_other_tags(system_prompt):
    assert "<cv>" not in system_prompt and "<offer>" not in system_prompt