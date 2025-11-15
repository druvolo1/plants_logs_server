# Phase Template Management Endpoints
# Add these to main.py after the plant creation endpoint

# ============ PHASE TEMPLATE ENDPOINTS ============

# List all phase templates for user
@app.get("/user/phase-templates", response_model=List[PhaseTemplateRead])
async def list_phase_templates(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get all phase templates for the current user"""
    from datetime import datetime

    result = await session.execute(
        select(PhaseTemplate)
        .where(PhaseTemplate.user_id == user.id)
        .order_by(PhaseTemplate.name)
    )
    templates = result.scalars().all()

    return templates

# Create a new phase template
@app.post("/user/phase-templates", response_model=PhaseTemplateRead)
async def create_phase_template(
    template_data: PhaseTemplateCreate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    """Create a new phase template"""
    from datetime import datetime

    new_template = PhaseTemplate(
        name=template_data.name,
        description=template_data.description,
        user_id=user.id,
        expected_seed_days=template_data.expected_seed_days,
        expected_clone_days=template_data.expected_clone_days,
        expected_veg_days=template_data.expected_veg_days,
        expected_flower_days=template_data.expected_flower_days,
        expected_drying_days=template_data.expected_drying_days,
        created_at=datetime.utcnow()
    )

    session.add(new_template)
    await session.commit()
    await session.refresh(new_template)

    return new_template

# Update a phase template
@app.patch("/user/phase-templates/{template_id}", response_model=PhaseTemplateRead)
async def update_phase_template(
    template_id: int,
    template_data: PhaseTemplateCreate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    """Update a phase template"""
    from datetime import datetime

    result = await session.execute(
        select(PhaseTemplate).where(
            PhaseTemplate.id == template_id,
            PhaseTemplate.user_id == user.id
        )
    )
    template = result.scalars().first()

    if not template:
        raise HTTPException(404, "Template not found")

    # Update fields
    template.name = template_data.name
    template.description = template_data.description
    template.expected_seed_days = template_data.expected_seed_days
    template.expected_clone_days = template_data.expected_clone_days
    template.expected_veg_days = template_data.expected_veg_days
    template.expected_flower_days = template_data.expected_flower_days
    template.expected_drying_days = template_data.expected_drying_days
    template.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(template)

    return template

# Delete a phase template
@app.delete("/user/phase-templates/{template_id}")
async def delete_phase_template(
    template_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
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
