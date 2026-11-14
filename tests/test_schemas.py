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
# ProfileEntry
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


###############################
# Profile
###############################

def test_profile_defaults_to_empty_lists():
    profile = Profile()
    assert profile.experience == []
    assert profile.education == []
    assert profile.courses == []
    assert profile.skills == []
    assert profile.languages == []
    assert profile.achievements == []

def test_profile_instances_do_not_share_lists():
    a = Profile()
    b = Profile()
    a.skills.append(ProfileEntry(title="Python"))
    assert b.skills == []

@pytest.mark.parametrize("count, valid", [(50, True), (51, False)])
def test_profile_section_length_limits(count, valid):
    entries = [ProfileEntry(title=f"Item {i}") for i in range(count)]
    print(f"Number of entries on Profile section: {len(entries)} Valid: {valid}")
    if valid:
        profile = Profile(skills=entries)
        assert len(profile.skills) == count
    else:
        with pytest.raises(ValidationError, match="skills"):
            Profile(skills=entries)

###############################
# ProfileResponse
###############################

def test_profile_response_builds_from_nested_dict():
    data = {
        "profile": {
            "skills": [{"title": "Python", "detail": "5 años"}],
            "experience": [{"title": "Backend developer"}],
        }
    }
    response = ProfileResponse(**data)

    assert isinstance(response.profile, Profile)
    assert isinstance(response.profile.skills[0], ProfileEntry)
    assert response.profile.skills[0].title == "Python"
    assert response.profile.skills[0].detail == "5 años"
    assert response.profile.experience[0].detail == ""   # default
    assert response.profile.education == []              # Omitted section


###############################
# ProfileConfirmRequest
###############################
def test_profile_confirm_request_builds_from_nested_dict():
    data = {
        "profile": {
            "skills": [
                {"title": "Ciberseguridad", "detail": "5 años"}, 
                {"title": "Python", "detail": "5 años"}
            ],
            "experience": [
                {"title": "Backend developer","detail": "Mas de 5 años"},
                {"title": "Ciberserguridad", "detail": "5 años"}
            ],
        }
    }
    request = ProfileConfirmRequest(**data)

    assert isinstance(request.profile, Profile)
    assert isinstance(request.profile.skills[0], ProfileEntry)
    assert request.profile.skills[0].title == "Ciberseguridad"
    assert request.profile.skills[0].detail == "5 años"
    assert request.profile.experience[0].title == "Backend developer"
    assert request.profile.experience[0].detail == "Mas de 5 años"
    assert request.profile.education == []

@pytest.mark.parametrize("title, valid", [("", False),("   ", False), ("A" * 201, False), ("A" * 20, True)])
def test_profile_confirm_request_rejects_invalid_nested_entry(title, valid):
    data = {
        "profile": {
            "skills": [
                {"title": title, "detail": "5 años"}, 
            ],
            "experience": [
                {"title": "Backend developer","detail": "Mas de 5 años"}
            ],
        }
    }
    print(f"Title length: {len(title)} Valid: {valid}")
    if valid:
        request = ProfileConfirmRequest(**data)
    else:
        with pytest.raises(ValidationError, match='title'):
            request = ProfileConfirmRequest(**data)

###############################
# OfferRequest
###############################

@pytest.mark.parametrize(
    "offer, valid",
    [("a"*9, False), ("a"*10, True), ("a"*8000, True), ("a"*8001, False), (""*5, False)],
)
def test_offer_request_length_limits(offer, valid):
    print(f"Offer length: {len(offer)} Valid: {valid}")
    if valid:
        assert OfferRequest(offer=offer).offer == offer
    else:
        with pytest.raises(ValidationError):
            OfferRequest(offer=offer)

def test_offer_request_rejects_whitespace_only_offer():
    with pytest.raises(ValidationError, match='offer'):
        OfferRequest(offer="   ")

###############################
# OfferRequirement
###############################

@pytest.mark.parametrize("status", ["ok", "partial", "ko", "", " ", "a"*80])
def test_offer_requirement_rejects_invalid_status(status):
    print(f"Offer requirement status: {status}")
    with pytest.raises(ValidationError, match='status'):
        OfferRequirement(status=status)

@pytest.mark.parametrize("status", ["OK", "Partial", "KO"])
def test_offer_requirement_accepts_valid_statuses(status):
    offer_requirement = OfferRequirement(text="Offer text", status=status)
    assert isinstance(offer_requirement, OfferRequirement)
    assert offer_requirement.status == status

def test_offer_requirement_evidence_defaults_to_none():
    offer_requirement = OfferRequirement(text="Offer text", status="OK")
    assert isinstance(offer_requirement, OfferRequirement)
    assert offer_requirement.evidence == None

###############################
# OfferResponse
###############################

@pytest.mark.parametrize("score", [-1, 101, 150])
def test_offer_response_rejects_score_out_of_range(score):
    with pytest.raises(ValidationError, match="score"):
        OfferResponse(score=score, requirements=[])

@pytest.mark.parametrize("score", [0, 100])
def test_offer_response_accepts_score_boundaries(score):
    offer_response = OfferResponse(score=score, requirements=[])
    assert isinstance(offer_response, OfferResponse)
    assert offer_response.score == score

def test_offer_response_rejects_invalid_requirement_status():
    data = {
        "score": 80,
        "requirements": [
            {"text": "Python", "status": "OK"},
            {"text": "Docker", "status": "Quizá"},
        ],
    }
    with pytest.raises(ValidationError, match="status"):
        OfferResponse(**data)