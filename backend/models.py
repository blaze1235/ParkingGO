"""Pydantic request/response schemas for the REST API."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Point = list[float]  # [x, y] in source-frame pixels


class LoginRequest(BaseModel):
    username: str
    password: str


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source_type: Literal["url", "file", "webcam"] = "url"
    source: str = Field(min_length=1, max_length=2000)


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    source_type: Optional[Literal["url", "file", "webcam"]] = None
    source: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    enabled: Optional[bool] = None


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    polygon: list[Point] = Field(min_length=3, max_length=32)
    side: Literal["left", "right"] = "right"
    position: int = 0

    @field_validator("polygon")
    @classmethod
    def check_points(cls, poly: list[Point]) -> list[Point]:
        for pt in poly:
            if len(pt) != 2:
                raise ValueError("each polygon point must be [x, y]")
        return poly


class ZoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    polygon: Optional[list[Point]] = Field(default=None, min_length=3, max_length=32)
    side: Optional[Literal["left", "right"]] = None
    position: Optional[int] = None
