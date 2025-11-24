# app/routers/templates.py
"""
Phase template management endpoints.
"""
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, PhaseTemplate
from app.schemas import PhaseTemplateCreate, PhaseTemplateRead

router = APIRouter(prefix="/user/phase-templates", tags=["templates"])


def get_current_user():
    """Import and return current_user dependency - imported here to avoid circular imports"""
    from app.main import current_user
    return current_user


def get_db():
    """Import and return get_db dependency - imported here to avoid circular imports"""
    from app.main import get_db as _get_db
    return _get_db


@router.get("", response_model=List[PhaseTemplateRead])
async def list_phase_templates(
    user: User = Depends(get_current_user()),
    session: AsyncSession = Depends(get_db())
):
    """Get all phase templates for the current user"""
    result = await session.execute(
        select(PhaseTemplate)
        .where(PhaseTemplate.user_id == user.id)
        .order_by(PhaseTemplate.name)
    )
    templates = result.scalars().all()
    return templates


@router.post("", response_model=PhaseTemplateRead)
async def create_phase_template(
    template_data: PhaseTemplateCreate,
    user: User = Depends(get_current_user()),
    session: AsyncSession = Depends(get_db())
):
    """Create a new phase template"""
    new_template = PhaseTemplate(
        name=template_data.name,
        description=template_data.description,
        user_id=user.id,
        expected_seed_days=template_data.expected_seed_days,
        expected_clone_days=template_data.expected_clone_days,
        expected_veg_days=template_data.expected_veg_days,
        expected_flower_days=template_data.expected_flower_days,
        expected_drying_days=template_data.expected_drying_days,
        expected_curing_days=template_data.expected_curing_days,
        created_at=datetime.utcnow()
    )

    session.add(new_template)
    await session.commit()
    await session.refresh(new_template)

    return new_template


@router.patch("/{template_id}", response_model=PhaseTemplateRead)
async def update_phase_template(
    template_id: int,
    template_data: PhaseTemplateCreate,
    user: User = Depends(get_current_user()),
    session: AsyncSession = Depends(get_db())
):
    """Update a phase template"""
    result = await session.execute(
        select(PhaseTemplate).where(
            PhaseTemplate.id == template_id,
            PhaseTemplate.user_id == user.id
        )
    )
    template = result.scalars().first()

    if not template:
        raise HTTPException(404, "Template not found")

    template.name = template_data.name
    template.description = template_data.description
    template.expected_seed_days = template_data.expected_seed_days
    template.expected_clone_days = template_data.expected_clone_days
    template.expected_veg_days = template_data.expected_veg_days
    template.expected_flower_days = template_data.expected_flower_days
    template.expected_drying_days = template_data.expected_drying_days
    template.expected_curing_days = template_data.expected_curing_days
    template.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(template)

    return template


@router.delete("/{template_id}")
async def delete_phase_template(
    template_id: int,
    user: User = Depends(get_current_user()),
    session: AsyncSession = Depends(get_db())
):
    """Delete a phase template"""
    result = await session.execute(
        select(PhaseTemplate).where(
            PhaseTemplate.id == template_id,
            PhaseTemplate.user_id == user.id
        )
    )
    template = result.scalars().first()

    if not template:
        raise HTTPException(404, "Template not found")

    await session.delete(template)
    await session.commit()

    return {"message": "Template deleted successfully"}
