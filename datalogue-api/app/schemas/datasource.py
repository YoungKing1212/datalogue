from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DatasourceCreate(BaseModel):
    name: str
    db_type: str = "postgres"
    host: str
    port: int = 5432
    database_name: str
    username: str
    password: str


class DatasourceUpdate(BaseModel):
    name: Optional[str] = None
    db_type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class DatasourceOut(BaseModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    database_name: str
    username: str
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
