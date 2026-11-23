"""Nodes of the matching graph. Each one is a function: state in, partial state out.

All of them are empty on purpose: step 3 is built one node at a time.
Suggested order (each step can be tested alone with a fake chain, like cv_extraction):
  1. extract_profile       (reuse structure_profile from app.services.cv_extraction)
  2. extract_requirements  (same technique: flat schema + with_structured_output)
  3. review_human          (interrupt, needs a checkpointer)
  4. evaluate
  5. verify_evidence
  6. compute_score
"""
from app.graph.state import MatchState


def extract_profile(state: MatchState) -> dict:
    """CV text -> Profile. Writes `profile`."""
    raise NotImplementedError


def extract_requirements(state: MatchState) -> dict:
    """Offer text -> list of requirements. Writes `requirements`."""
    raise NotImplementedError


def review_human(state: MatchState) -> dict:
    """Pause the graph so the user can edit profile and requirements (HITL).

    Keep this node alone: when the graph resumes, the node runs again from its first line,
    so an LLM call inside it would be repeated.
    """
    raise NotImplementedError


def evaluate(state: MatchState) -> dict:
    """Compare every requirement with the profile. Writes `evaluations` and `attempts`."""
    raise NotImplementedError


def verify_evidence(state: MatchState) -> dict:
    """Check that each evidence really appears in the profile (code, no LLM)."""
    raise NotImplementedError


def compute_score(state: MatchState) -> dict:
    """Score computed in code (never by the LLM). Writes `result`."""
    raise NotImplementedError