"""State shared by all the nodes of the matching graph (step 3).

Every node receives the whole state and returns only the keys it wants to update.
Plain TypedDict for now: nothing from LangGraph is imported yet.
"""
from typing import TypedDict

from app.schemas import OfferRequirement, OfferResponse, Profile


class MatchState(TypedDict, total=False):
    # --- Inputs (filled by run_match before the graph starts) ---
    cv_text: str       # raw text of the CV (step 1)
    offer_text: str    # raw text of the job offer (step 2)

    # --- Extraction (two independent branches, planned to run in parallel) ---
    profile: Profile           # written by extract_profile
    requirements: list[str]    # written by extract_requirements

    # --- Human review (HITL): the user can correct profile and requirements ---
    # TODO(step 3b): decide which fields the review adds (for example `approved: bool`).

    # --- Match ---
    evaluations: list[OfferRequirement]  # written by evaluate (status + evidence per requirement)
    attempts: int                        # evaluate retries, to stop the review loop
    result: OfferResponse                # written by compute_score: the final answer