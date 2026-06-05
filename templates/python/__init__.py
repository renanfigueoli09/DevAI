"""
Template Python — FastAPI + Clean Architecture.
Padrões: Repository, Service, Pydantic schemas, pytest.
"""

MODULE_TEMPLATE = '''
# ═══════════════════════════════════════════════════════════════════════════════
# ESTRUTURA DE MÓDULO FASTAPI — CLEAN ARCHITECTURE
# ═══════════════════════════════════════════════════════════════════════════════
#
# src/
#  └── {{name}}/
#      ├── __init__.py
#      ├── router.py              ← FastAPI router (HTTP layer)
#      ├── service.py             ← Application layer (use cases)
#      ├── repository.py          ← Data access (SQLAlchemy)
#      ├── models.py              ← SQLAlchemy models
#      ├── schemas.py             ← Pydantic schemas (DTO)
#      ├── interfaces.py          ← ABCs / Protocols (DIP)
#      ├── exceptions.py          ← Domain-specific errors
#      └── tests/
#          ├── test_service.py
#          └── test_router.py

# ─── interfaces.py (DIP — Dependency Inversion) ────────────────────────────
from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID


class {{Name}}RepositoryInterface(ABC):
    @abstractmethod
    async def find_all(self) -> list: ...

    @abstractmethod
    async def find_by_id(self, id: UUID) -> Optional[object]: ...

    @abstractmethod
    async def create(self, data: dict) -> object: ...

    @abstractmethod
    async def update(self, id: UUID, data: dict) -> Optional[object]: ...

    @abstractmethod
    async def delete(self, id: UUID) -> bool: ...


# ─── models.py (SQLAlchemy) ─────────────────────────────────────────────────
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from database import Base  # ← importar o Base do seu projeto
import uuid


class {{Name}}Model(Base):
    __tablename__ = "{{name_plural}}"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ← adicionar colunas do domínio aqui
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ─── schemas.py (Pydantic) ──────────────────────────────────────────────────
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Optional


class {{Name}}Base(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name field")
    # ← adicionar campos do domínio


class {{Name}}Create({{Name}}Base):
    pass


class {{Name}}Update(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    # ← tornar todos os campos opcionais (partial update)


class {{Name}}Response({{Name}}Base):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None


# ─── exceptions.py ──────────────────────────────────────────────────────────
from fastapi import HTTPException, status


class {{Name}}NotFoundException(HTTPException):
    def __init__(self, id):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{{Name}} with id '{id}' not found",
        )


class {{Name}}AlreadyExistsException(HTTPException):
    def __init__(self, field: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{{Name}} with this {field} already exists",
        )


# ─── repository.py ──────────────────────────────────────────────────────────
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Optional

from .interfaces import {{Name}}RepositoryInterface
from .models import {{Name}}Model


class {{Name}}Repository({{Name}}RepositoryInterface):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_all(self) -> list[{{Name}}Model]:
        result = await self.session.execute(
            select({{Name}}Model).order_by({{Name}}Model.created_at.desc())
        )
        return result.scalars().all()

    async def find_by_id(self, id: UUID) -> Optional[{{Name}}Model]:
        result = await self.session.execute(
            select({{Name}}Model).where({{Name}}Model.id == id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> {{Name}}Model:
        obj = {{Name}}Model(**data)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def update(self, id: UUID, data: dict) -> Optional[{{Name}}Model]:
        obj = await self.find_by_id(id)
        if not obj:
            return None
        for key, value in data.items():
            setattr(obj, key, value)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete(self, id: UUID) -> bool:
        obj = await self.find_by_id(id)
        if not obj:
            return False
        await self.session.delete(obj)
        await self.session.commit()
        return True


# ─── service.py ─────────────────────────────────────────────────────────────
from uuid import UUID
from .interfaces import {{Name}}RepositoryInterface
from .schemas import {{Name}}Create, {{Name}}Update
from .exceptions import {{Name}}NotFoundException


class {{Name}}Service:
    def __init__(self, repository: {{Name}}RepositoryInterface):
        self.repository = repository  # DIP: recebe interface, não implementação

    async def find_all(self):
        return await self.repository.find_all()

    async def find_by_id(self, id: UUID):
        obj = await self.repository.find_by_id(id)
        if not obj:
            raise {{Name}}NotFoundException(id)
        return obj

    async def create(self, data: {{Name}}Create):
        return await self.repository.create(data.model_dump())

    async def update(self, id: UUID, data: {{Name}}Update):
        await self.find_by_id(id)  # valida existência
        obj = await self.repository.update(id, data.model_dump(exclude_unset=True))
        return obj

    async def delete(self, id: UUID) -> None:
        await self.find_by_id(id)  # valida existência
        await self.repository.delete(id)


# ─── router.py ──────────────────────────────────────────────────────────────
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Annotated

from database import get_session  # ← importar do seu projeto
from .service import {{Name}}Service
from .repository import {{Name}}Repository
from .schemas import {{Name}}Create, {{Name}}Update, {{Name}}Response


router = APIRouter(prefix="/{{name_plural}}", tags=["{{name_plural}}"])


def get_service(session: Annotated[AsyncSession, Depends(get_session)]) -> {{Name}}Service:
    return {{Name}}Service({{Name}}Repository(session))


@router.get("/", response_model=list[{{Name}}Response])
async def list_{{name_plural}}(service: Annotated[{{Name}}Service, Depends(get_service)]):
    return await service.find_all()


@router.get("/{id}", response_model={{Name}}Response)
async def get_{{name}}(id: UUID, service: Annotated[{{Name}}Service, Depends(get_service)]):
    return await service.find_by_id(id)


@router.post("/", response_model={{Name}}Response, status_code=status.HTTP_201_CREATED)
async def create_{{name}}(data: {{Name}}Create, service: Annotated[{{Name}}Service, Depends(get_service)]):
    return await service.create(data)


@router.put("/{id}", response_model={{Name}}Response)
async def update_{{name}}(id: UUID, data: {{Name}}Update, service: Annotated[{{Name}}Service, Depends(get_service)]):
    return await service.update(id, data)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_{{name}}(id: UUID, service: Annotated[{{Name}}Service, Depends(get_service)]):
    await service.delete(id)


# ─── tests/test_service.py ───────────────────────────────────────────────────
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from {{name}}.service import {{Name}}Service
from {{name}}.schemas import {{Name}}Create
from {{name}}.exceptions import {{Name}}NotFoundException


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    return {{Name}}Service(mock_repo)


@pytest.mark.asyncio
async def test_find_by_id_raises_when_not_found(service, mock_repo):
    mock_repo.find_by_id.return_value = None
    with pytest.raises({{Name}}NotFoundException):
        await service.find_by_id(uuid4())


@pytest.mark.asyncio
async def test_create_returns_created_object(service, mock_repo):
    data = {{Name}}Create(name="Test")
    mock_repo.create.return_value = MagicMock(id=uuid4(), name="Test")
    result = await service.create(data)
    assert result.name == "Test"
    mock_repo.create.assert_called_once()
'''

DESCRIPTION = "FastAPI + SQLAlchemy async + Pydantic v2 + pytest + Clean Architecture"
TECH_STACK = ["FastAPI", "Python 3.12", "SQLAlchemy 2.0", "Alembic", "Pydantic v2", "pytest", "asyncpg"]
