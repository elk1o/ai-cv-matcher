import operator
from typing import TypedDict, Annotated, List, Literal

from app.schemas import OfferRequirement, OfferResponse, Profile


class MatchState(TypedDict, total=False):
    # --- Inputs (filled by run_match before the graph starts) ---
    cv_text: str       # raw text of the CV (step 1)
    offer_text: str    # raw text of the job offer (step 2)

    profile: Profile           # written by extract_profile
    requirements: List[str]    # written by extract_requirements

    # --- Match ---
    evaluations: List[OfferRequirement]  # written by evaluate (status + evidence per requirement)
    attempts: int                        # evaluate retries, to stop the review loop
    result: OfferResponse                # written by compute_score: the final answer

    log: Annotated[List[str], operator.add]