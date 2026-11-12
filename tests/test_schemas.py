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
