from typing import Any

from pydantic import BaseModel, Field


class RentalRequest(BaseModel):
    table: str = ""
    action: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

