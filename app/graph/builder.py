"""Builds and runs the matching graph (step 3).

Planned graph (nothing of this is built yet):

    START --> extract_profile ------+
      |                             +--> review_human --> evaluate --> verify_evidence --> compute_score --> END
      +-----> extract_requirements -+                        ^               |
                                                             +---------------+  (conditional edge:
                                                                                  retry, with a limit)
"""
from app.graph.state import MatchState  # noqa: F401  (used when the graph is built)
from app.schemas import OfferResponse


def build_graph():
    """Create and compile the StateGraph. TODO(step 3)."""
    raise NotImplementedError


def run_match(cv_text: str, offer_text: str) -> OfferResponse:
    """Run the graph with the two raw texts and return the final answer.

    The router translates NotImplementedError into 501 while the graph does not exist.
    """
    raise NotImplementedError