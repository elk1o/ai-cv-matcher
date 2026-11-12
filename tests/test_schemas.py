import pytest
from pydantic import ValidationError

from app.schemas import (
    ProfileEntry,
    Profile,
    ProfileResponse,
    ProfileConfirmRequest,
    OfferRequest,
    OfferRequirement,
    OfferResponse,
)

###############################
# 1. ProfileEntry
###############################

# Test to handle empty title on ProfileEntry
def test_profile_entry_rejects_empty_title():
    with pytest.raises(ValidationError, match="title"):
        ProfileEntry(title="")

# Test to handle incorrect title length on ProfileEntry
@pytest.mark.parametrize("length, valid", [(0, False), (1, True), (200, True), (201, False), (2000, False)])
def test_profile_entry_title_length_limits(length, valid):
    title = "A" * length
    print(f"Title length: {len(title)} Valid: {valid}")

    if valid:
        entry = ProfileEntry(title=title)
        assert entry.title == title
    else:
        with pytest.raises(ValidationError, match='title'):
            ProfileEntry(title=title)

def test_profile_entry_rejects_whitespace_only_title():
    with pytest.raises(ValidationError, match='title'):
        entry = ProfileEntry(title="   ")

@pytest.mark.parametrize("length, valid", [(2000, True), (2001, False)])
def test_profile_entry_detail_length_limits(length, valid):
    detail = "A" * length
    print(f"Description length: {len(detail)} Valid: {valid}")

    if valid:
        entry = ProfileEntry(title="AA", detail=detail)
        assert entry.detail == detail
    else:
        with pytest.raises(ValidationError, match='detail'):
            ProfileEntry(title="AA", detail=detail)

def test_profile_entry_detail_defaults_to_empty_string():
    entry = ProfileEntry(title="AA")
    assert entry.detail == ""

def test_profile_entry_strips_whitespace():
    entry = ProfileEntry(title="  test  ")
    assert entry.title == "test"


# # --- 2. Profile: perfil completo extraído del CV (POST /cv) ---
# def test_profile_defaults_to_empty_lists():
#     pass


# def test_profile_instances_do_not_share_lists():
#     pass


# @pytest.mark.parametrize("count, valid", [(50, True), (51, False)])
# def test_profile_section_length_limits(count, valid):
#     pass


# # --- 3. ProfileResponse: respuesta de POST /cv ---
# def test_profile_response_builds_from_nested_dict():
#     pass


# # --- 4. ProfileConfirmRequest: entrada de POST /cv/confirm ---
# def test_profile_confirm_request_builds_from_nested_dict():
#     pass


# def test_profile_confirm_request_rejects_invalid_nested_entry():
#     pass


# # --- 5. OfferRequest: entrada de POST /offer ---
# @pytest.mark.parametrize(
#     "length, valid",
#     [(9, False), (10, True), (8000, True), (8001, False)],
# )
# def test_offer_request_length_limits(length, valid):
#     offer = "a" * length
#     if valid:
#         assert OfferRequest(offer=offer).offer == offer
#     else:
#         with pytest.raises(ValidationError):
#             OfferRequest(offer=offer)


# def test_offer_request_rejects_whitespace_only_offer():
#     pass


# # --- 6. OfferRequirement: un requisito evaluado (dentro de la respuesta de POST /offer) ---
# def test_offer_requirement_rejects_invalid_status():
#     pass


# @pytest.mark.parametrize("status", ["OK", "Partial", "KO"])
# def test_offer_requirement_accepts_valid_statuses(status):
#     pass


# def test_offer_requirement_evidence_defaults_to_none():
#     pass


# # --- 7. OfferResponse: respuesta de POST /offer ---
# @pytest.mark.parametrize("score", [-1, 101, 150])
# def test_offer_response_rejects_score_out_of_range(score):
#     with pytest.raises(ValidationError):
#         OfferResponse(score=score, requirements=[])


# @pytest.mark.parametrize("score", [0, 100])
# def test_offer_response_accepts_score_boundaries(score):
#     pass


# def test_offer_response_rejects_invalid_requirement_status():
#     pass