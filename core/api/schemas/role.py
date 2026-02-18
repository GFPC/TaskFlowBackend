# core/api/schemas/role.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    permissions: Optional[str] = None
    priority: int = 0


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = None
    permissions: Optional[str] = None
    priority: Optional[int] = None


class RoleResponse(RoleBase):
    id: int

    class Config:
        from_attributes = True