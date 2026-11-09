from typing import Literal

from pydantic import BaseModel, Field


class ProfileEntry(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=2000)

class Profile(BaseModel):
    experience: list[ProfileEntry] = Field(default_factory=list, max_length=50)
    education: list[ProfileEntry] = Field(default_factory=list, max_length=50)
    courses: list[ProfileEntry] = Field(default_factory=list, max_length=50)
    skills: list[ProfileEntry] = Field(default_factory=list, max_length=50)
    languages: list[ProfileEntry] = Field(default_factory=list, max_length=50)
    achievements: list[ProfileEntry] = Field(default_factory=list, max_length=50)

class ProfileResponse(BaseModel):
    profile: Profile

class ProfileConfirmRequest(BaseModel):
    profile: Profile

class OfferRequest(BaseModel):
    offer: str = Field(min_length=10, max_length=8000)

class OfferRequirement(BaseModel):
    text: str
    status: Literal["OK", "Partial", "KO"]
    evidence: str | None = None

class OfferResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    requirements: list[OfferRequirement]

