"""
Release request models
"""
from typing import Optional
from pydantic import BaseModel, Field


class ReleaseCopyRequest(BaseModel):
    track_title: str
    artist_name: str
    genre: str
    mood: str
    lyrics: Optional[str] = ""


class MetadataRequest(BaseModel):
    track_title: str
    artist_name: str
    mood: str
    genre: str
    explicit: bool = False
    release_date: str

