"""Request schemas for API endpoints"""

from pydantic import BaseModel, Field
from typing import List, Optional


class StoreSubmissionsRequest(BaseModel):
    """Request schema for storing submissions"""
    submissions: List[str] = Field(..., min_length=1, description="List of submission texts to store")


class CreateDebateRequest(BaseModel):
    """Request schema for creating a debate"""
    max_rounds: Optional[int] = Field(None, ge=1, le=50, description="Maximum number of debate rounds")
    max_messages: Optional[int] = Field(None, ge=1, le=200, description="Maximum number of messages")

