# app/routers/social.py
"""
Social media feature endpoints: profiles, published reports, reviews, and discovery.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
import json

from app.models import (
    User, Plant, PlantReport,
    GrowerProfile, ProductLocation, PublishedReport, UpcomingStrain,
    StrainReview, ReviewResponse, AdminSetting
)
from app.schemas.social import (
    GrowerProfileCreate, GrowerProfileUpdate, GrowerProfileRead,
    ProductLocationCreate, ProductLocationUpdate, ProductLocationRead,
    PublishedReportCreate, PublishedReportRead, PublishedReportSummary,
    UpcomingStrainCreate, UpcomingStrainRead,
    StrainReviewCreate, StrainReviewUpdate, StrainReviewRead,
    ReviewResponseCreate, ReviewResponseUpdate, ReviewResponseRead,
    AdminSettingUpdate, AdminSettingRead
)
from app.dependencies import get_current_user_dependency, get_db_dependency, get_optional_user, require_superuser

router = APIRouter(prefix="/api/social", tags=["social"])


# ===== HELPER FUNCTIONS =====

async def _build_profile_read(session: AsyncSession, profile: GrowerProfile, user: User) -> GrowerProfileRead:
    """Build GrowerProfileRead with computed fields"""
    # Count published reports
    reports_count = await session.execute(
        select(func.count(PublishedReport.id)).where(
            PublishedReport.user_id == user.id,
            PublishedReport.unpublished_at.is_(None)
        )
    )
    total_reports = reports_count.scalar() or 0

    # Calculate average rating from all published reports
    avg_rating_result = await session.execute(
        select(func.avg(StrainReview.rating)).select_from(PublishedReport).join(
            StrainReview, StrainReview.published_report_id == PublishedReport.id
        ).where(
            PublishedReport.user_id == user.id,
            PublishedReport.unpublished_at.is_(None)
        )
    )
    avg_rating = avg_rating_result.scalar()

    # Count total reviews
    review_count = await session.execute(
        select(func.count(StrainReview.id)).select_from(PublishedReport).join(
            StrainReview, StrainReview.published_report_id == PublishedReport.id
        ).where(
            PublishedReport.user_id == user.id,
            PublishedReport.unpublished_at.is_(None)
        )
    )
    total_reviews = review_count.scalar() or 0

    # Grower name
    grower_name = profile.business_name or f"{user.first_name} {user.last_name}".strip() or user.email

    return GrowerProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        business_name=profile.business_name,
        bio=profile.bio,
        location=profile.location,
        website=profile.website,
        instagram=profile.instagram,
        is_public=profile.is_public,
        created_at=profile.created_at,
        grower_name=grower_name,
        total_published_reports=total_reports,
        average_rating=round(avg_rating, 1) if avg_rating else None,
        total_reviews=total_reviews
    )


async def _build_published_report_read(session: AsyncSession, report: PublishedReport, user: User) -> PublishedReportRead:
    """Build PublishedReportRead with grower info"""
    profile_result = await session.execute(
        select(GrowerProfile).where(GrowerProfile.user_id == user.id)
    )
    profile = profile_result.scalars().first()

    grower_name = f"{user.first_name} {user.last_name}".strip() or user.email
    grower_business_name = profile.business_name if profile else None

    # Calculate average rating and count reviews
    avg_rating_result = await session.execute(
        select(func.avg(StrainReview.rating)).where(StrainReview.published_report_id == report.id)
    )
    avg_rating = avg_rating_result.scalar()

    review_count = await session.execute(
        select(func.count(StrainReview.id)).where(StrainReview.published_report_id == report.id)
    )
    total_reviews = review_count.scalar() or 0

    return PublishedReportRead(
        id=report.id,
        user_id=report.user_id,
        plant_id=report.plant_id,
        plant_name=report.plant_name,
        strain=report.strain,
        start_date=report.start_date,
        end_date=report.end_date,
        final_phase=report.final_phase,
        report_data=report.report_data,
        published_at=report.published_at,
        views_count=report.views_count,
        grower_notes=report.grower_notes,
        grower_name=grower_name,
        grower_business_name=grower_business_name,
        average_rating=round(avg_rating, 1) if avg_rating else None,
        total_reviews=total_reviews
    )


async def _check_anonymous_browsing(session: AsyncSession) -> bool:
    """Check if anonymous browsing is enabled"""
    result = await session.execute(
        select(AdminSetting).where(AdminSetting.setting_key == 'allow_anonymous_browsing')
    )
    setting = result.scalars().first()
    return setting and setting.setting_value.lower() == 'true'


# ===== GROWER PROFILES =====

@router.post("/profile", response_model=GrowerProfileRead)
async def create_or_update_profile(
    profile_data: GrowerProfileUpdate,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Create or update current user's grower profile"""
    # Get or create profile
    result = await session.execute(
        select(GrowerProfile).where(GrowerProfile.user_id == current_user.id)
    )
    profile = result.scalars().first()

    if not profile:
        profile = GrowerProfile(user_id=current_user.id)
        session.add(profile)

    # Update fields
    for field, value in profile_data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    await session.commit()
    await session.refresh(profile)

    return await _build_profile_read(session, profile, current_user)


@router.get("/profile/me", response_model=GrowerProfileRead)
async def get_my_profile(
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get current user's grower profile"""
    result = await session.execute(
        select(GrowerProfile).where(GrowerProfile.user_id == current_user.id)
    )
    profile = result.scalars().first()

    if not profile:
        # Create default profile
        profile = GrowerProfile(user_id=current_user.id)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)

    return await _build_profile_read(session, profile, current_user)


@router.get("/profile/{user_id}", response_model=GrowerProfileRead)
async def get_grower_profile(
    user_id: int,
    session: AsyncSession = Depends(get_db_dependency()),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Get a grower's public profile"""
    result = await session.execute(
        select(GrowerProfile).where(GrowerProfile.user_id == user_id)
    )
    profile = result.scalars().first()

    if not profile or not profile.is_public:
        raise HTTPException(404, "Grower profile not found or not public")

    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()

    return await _build_profile_read(session, profile, user)


@router.get("/growers", response_model=List[GrowerProfileRead])
async def browse_growers(
    skip: int = 0,
    limit: int = 20,
    sort_by: str = Query("recent", regex="^(recent|reports)$"),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Browse all public grower profiles"""
    query = select(GrowerProfile).where(GrowerProfile.is_public == True)

    if sort_by == "recent":
        query = query.order_by(desc(GrowerProfile.created_at))
    # Note: sorting by rating/reports requires subquery - implement if needed

    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    profiles = result.scalars().all()

    # Build response for each
    response = []
    for profile in profiles:
        user_result = await session.execute(select(User).where(User.id == profile.user_id))
        user = user_result.scalars().first()
        response.append(await _build_profile_read(session, profile, user))

    return response


# ===== PRODUCT LOCATIONS =====

@router.post("/product-locations", response_model=ProductLocationRead)
async def add_product_location(
    location_data: ProductLocationCreate,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Add product location to current user's profile"""
    location = ProductLocation(
        user_id=current_user.id,
        **location_data.model_dump()
    )
    session.add(location)
    await session.commit()
    await session.refresh(location)

    return location


@router.put("/product-locations/{location_id}", response_model=ProductLocationRead)
async def update_product_location(
    location_id: int,
    location_data: ProductLocationUpdate,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update a product location"""
    result = await session.execute(
        select(ProductLocation).where(ProductLocation.id == location_id)
    )
    location = result.scalars().first()

    if not location or location.user_id != current_user.id:
        raise HTTPException(404, "Product location not found")

    for field, value in location_data.model_dump(exclude_unset=True).items():
        setattr(location, field, value)

    await session.commit()
    await session.refresh(location)

    return location


@router.delete("/product-locations/{location_id}")
async def remove_product_location(
    location_id: int,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Remove a product location"""
    result = await session.execute(
        select(ProductLocation).where(ProductLocation.id == location_id)
    )
    location = result.scalars().first()

    if not location or location.user_id != current_user.id:
        raise HTTPException(404, "Product location not found")

    await session.delete(location)
    await session.commit()

    return {"message": "Product location removed"}


@router.get("/product-locations/me", response_model=List[ProductLocationRead])
async def get_my_product_locations(
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get current user's product locations"""
    result = await session.execute(
        select(ProductLocation).where(ProductLocation.user_id == current_user.id)
    )
    return result.scalars().all()


@router.get("/product-locations/{user_id}", response_model=List[ProductLocationRead])
async def get_grower_product_locations(
    user_id: int,
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get a grower's product locations (public)"""
    # Verify profile is public
    profile_result = await session.execute(
        select(GrowerProfile).where(GrowerProfile.user_id == user_id)
    )
    profile = profile_result.scalars().first()

    if not profile or not profile.is_public:
        raise HTTPException(404, "Grower profile not found or not public")

    result = await session.execute(
        select(ProductLocation).where(ProductLocation.user_id == user_id)
    )
    return result.scalars().all()


# ===== PUBLISHED REPORTS =====

@router.post("/reports/publish", response_model=PublishedReportRead)
async def publish_report(
    report_create: PublishedReportCreate,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Publish a completed plant report"""
    # Verify plant belongs to user
    plant_result = await session.execute(
        select(Plant).where(Plant.plant_id == report_create.plant_id)
    )
    plant = plant_result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Verify ownership
    if plant.user_id != current_user.id:
        raise HTTPException(403, "Not authorized to publish this plant's report")

    # Get plant report
    report_result = await session.execute(
        select(PlantReport).where(PlantReport.plant_id == plant.id)
    )
    plant_report = report_result.scalars().first()

    if not plant_report:
        raise HTTPException(400, "Plant report not generated yet. Mark plant as finished first.")

    # Check if already published
    existing = await session.execute(
        select(PublishedReport).where(
            PublishedReport.plant_id == report_create.plant_id,
            PublishedReport.unpublished_at.is_(None)
        )
    )
    if existing.scalars().first():
        raise HTTPException(400, "Report already published")

    # Create published report
    published = PublishedReport(
        user_id=current_user.id,
        plant_id=plant.plant_id,
        plant_name=plant_report.plant_name,
        strain=plant_report.strain,
        start_date=plant_report.start_date,
        end_date=plant_report.end_date,
        final_phase=plant_report.final_phase,
        report_data={
            "raw_data": json.loads(plant_report.raw_data) if isinstance(plant_report.raw_data, str) else plant_report.raw_data,
            "aggregated_stats": json.loads(plant_report.aggregated_stats) if isinstance(plant_report.aggregated_stats, str) else plant_report.aggregated_stats
        },
        grower_notes=report_create.grower_notes
    )

    session.add(published)
    await session.commit()
    await session.refresh(published)

    return await _build_published_report_read(session, published, current_user)


@router.post("/reports/{report_id}/unpublish")
async def unpublish_report(
    report_id: int,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Unpublish a report (soft delete)"""
    result = await session.execute(
        select(PublishedReport).where(PublishedReport.id == report_id)
    )
    report = result.scalars().first()

    if not report:
        raise HTTPException(404, "Published report not found")

    if report.user_id != current_user.id:
        raise HTTPException(403, "Not authorized to unpublish this report")

    # Soft delete
    report.unpublished_at = datetime.utcnow()
    await session.commit()

    return {"message": "Report unpublished successfully"}


@router.get("/reports/{report_id}", response_model=PublishedReportRead)
async def get_published_report(
    report_id: int,
    session: AsyncSession = Depends(get_db_dependency()),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Get a published report (public endpoint with anonymous browsing check)"""
    # Check if anonymous browsing is allowed
    if not current_user:
        if not await _check_anonymous_browsing(session):
            raise HTTPException(401, "Login required to view reports")

    result = await session.execute(
        select(PublishedReport).where(
            PublishedReport.id == report_id,
            PublishedReport.unpublished_at.is_(None)
        )
    )
    report = result.scalars().first()

    if not report:
        raise HTTPException(404, "Published report not found or has been unpublished")

    # Increment view count
    report.views_count += 1
    await session.commit()

    # Get grower info
    user_result = await session.execute(select(User).where(User.id == report.user_id))
    user = user_result.scalars().first()

    return await _build_published_report_read(session, report, user)


@router.get("/reports", response_model=List[PublishedReportSummary])
async def browse_reports(
    skip: int = 0,
    limit: int = 20,
    strain: Optional[str] = None,
    grower_id: Optional[int] = None,
    sort_by: str = Query("recent", regex="^(recent|views)$"),
    session: AsyncSession = Depends(get_db_dependency()),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """Browse published reports (public with anonymous browsing check)"""
    # Check if anonymous browsing is allowed
    if not current_user:
        if not await _check_anonymous_browsing(session):
            raise HTTPException(401, "Login required to browse reports")

    query = select(PublishedReport).where(PublishedReport.unpublished_at.is_(None))

    if strain:
        query = query.where(PublishedReport.strain.ilike(f"%{strain}%"))

    if grower_id:
        query = query.where(PublishedReport.user_id == grower_id)

    if sort_by == "recent":
        query = query.order_by(desc(PublishedReport.published_at))
    elif sort_by == "views":
        query = query.order_by(desc(PublishedReport.views_count))

    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    reports = result.scalars().all()

    # Build summaries
    summaries = []
    for report in reports:
        user_result = await session.execute(select(User).where(User.id == report.user_id))
        user = user_result.scalars().first()

        profile_result = await session.execute(select(GrowerProfile).where(GrowerProfile.user_id == user.id))
        profile = profile_result.scalars().first()

        grower_name = f"{user.first_name} {user.last_name}".strip() or user.email

        # Get average rating
        avg_rating_result = await session.execute(
            select(func.avg(StrainReview.rating)).where(StrainReview.published_report_id == report.id)
        )
        avg_rating = avg_rating_result.scalar()

        review_count = await session.execute(
            select(func.count(StrainReview.id)).where(StrainReview.published_report_id == report.id)
        )
        total_reviews = review_count.scalar() or 0

        summaries.append(PublishedReportSummary(
            id=report.id,
            plant_name=report.plant_name,
            strain=report.strain,
            end_date=report.end_date,
            published_at=report.published_at,
            views_count=report.views_count,
            grower_name=grower_name,
            grower_business_name=profile.business_name if profile else None,
            average_rating=round(avg_rating, 1) if avg_rating else None,
            total_reviews=total_reviews
        ))

    return summaries


# ===== UPCOMING STRAINS =====

@router.post("/strains/upcoming", response_model=UpcomingStrainRead)
async def add_upcoming_strain(
    strain_data: UpcomingStrainCreate,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Add an upcoming strain to current user's profile"""
    strain = UpcomingStrain(
        user_id=current_user.id,
        **strain_data.model_dump()
    )
    session.add(strain)
    await session.commit()
    await session.refresh(strain)

    return strain


@router.delete("/strains/upcoming/{strain_id}")
async def remove_upcoming_strain(
    strain_id: int,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Remove an upcoming strain"""
    result = await session.execute(
        select(UpcomingStrain).where(UpcomingStrain.id == strain_id)
    )
    strain = result.scalars().first()

    if not strain or strain.user_id != current_user.id:
        raise HTTPException(404, "Upcoming strain not found")

    await session.delete(strain)
    await session.commit()

    return {"message": "Upcoming strain removed"}


@router.get("/strains/upcoming/{user_id}", response_model=List[UpcomingStrainRead])
async def get_upcoming_strains(
    user_id: int,
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get upcoming strains for a grower"""
    # Verify profile is public
    profile_result = await session.execute(
        select(GrowerProfile).where(GrowerProfile.user_id == user_id)
    )
    profile = profile_result.scalars().first()

    if not profile or not profile.is_public:
        raise HTTPException(404, "Grower profile not found or not public")

    result = await session.execute(
        select(UpcomingStrain)
        .where(UpcomingStrain.user_id == user_id)
        .order_by(UpcomingStrain.expected_start_date)
    )
    return result.scalars().all()


# ===== STRAIN REVIEWS =====

@router.post("/reviews/{report_id}", response_model=StrainReviewRead)
async def submit_review(
    report_id: int,
    review_data: StrainReviewCreate,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Submit or update a review for a strain (published report)"""
    # Verify report exists and is published
    report_result = await session.execute(
        select(PublishedReport).where(
            PublishedReport.id == report_id,
            PublishedReport.unpublished_at.is_(None)
        )
    )
    report = report_result.scalars().first()

    if not report:
        raise HTTPException(404, "Published report not found")

    # Cannot review own report
    if report.user_id == current_user.id:
        raise HTTPException(400, "Cannot review your own report")

    # Check if review already exists
    existing_result = await session.execute(
        select(StrainReview).where(
            StrainReview.published_report_id == report_id,
            StrainReview.reviewer_id == current_user.id
        )
    )
    existing_review = existing_result.scalars().first()

    if existing_review:
        # Update existing review
        existing_review.rating = review_data.rating
        existing_review.comment = review_data.comment
        existing_review.updated_at = datetime.utcnow()
        review = existing_review
    else:
        # Create new review
        review = StrainReview(
            published_report_id=report_id,
            reviewer_id=current_user.id,
            **review_data.model_dump()
        )
        session.add(review)

    await session.commit()
    await session.refresh(review)

    reviewer_name = f"{current_user.first_name} {current_user.last_name}".strip() or current_user.email

    return StrainReviewRead(
        id=review.id,
        published_report_id=review.published_report_id,
        reviewer_id=review.reviewer_id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
        updated_at=review.updated_at,
        reviewer_name=reviewer_name,
        has_response=False,
        response=None
    )


@router.delete("/reviews/{review_id}")
async def delete_review(
    review_id: int,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Delete your review"""
    result = await session.execute(
        select(StrainReview).where(StrainReview.id == review_id)
    )
    review = result.scalars().first()

    if not review or review.reviewer_id != current_user.id:
        raise HTTPException(404, "Review not found")

    await session.delete(review)
    await session.commit()

    return {"message": "Review deleted"}


@router.get("/reviews/{report_id}", response_model=List[StrainReviewRead])
async def get_reviews(
    report_id: int,
    skip: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get all reviews for a published report"""
    result = await session.execute(
        select(StrainReview)
        .where(StrainReview.published_report_id == report_id)
        .order_by(desc(StrainReview.created_at))
        .offset(skip)
        .limit(limit)
    )
    reviews = result.scalars().all()

    # Build response with reviewer names and responses
    response = []
    for review in reviews:
        reviewer_result = await session.execute(
            select(User).where(User.id == review.reviewer_id)
        )
        reviewer = reviewer_result.scalars().first()
        reviewer_name = f"{reviewer.first_name} {reviewer.last_name}".strip() or reviewer.email

        # Get response if exists
        response_result = await session.execute(
            select(ReviewResponse).where(ReviewResponse.review_id == review.id)
        )
        review_response = response_result.scalars().first()

        response_data = None
        if review_response:
            grower_result = await session.execute(select(User).where(User.id == review_response.grower_id))
            grower = grower_result.scalars().first()
            grower_name = f"{grower.first_name} {grower.last_name}".strip() or grower.email

            response_data = ReviewResponseRead(
                id=review_response.id,
                review_id=review_response.review_id,
                grower_id=review_response.grower_id,
                response_text=review_response.response_text,
                created_at=review_response.created_at,
                updated_at=review_response.updated_at,
                grower_name=grower_name
            )

        response.append(StrainReviewRead(
            id=review.id,
            published_report_id=review.published_report_id,
            reviewer_id=review.reviewer_id,
            rating=review.rating,
            comment=review.comment,
            created_at=review.created_at,
            updated_at=review.updated_at,
            reviewer_name=reviewer_name,
            has_response=review_response is not None,
            response=response_data
        ))

    return response


# ===== REVIEW RESPONSES =====

@router.post("/reviews/{review_id}/response", response_model=ReviewResponseRead)
async def submit_response(
    review_id: int,
    response_data: ReviewResponseCreate,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Grower responds to a review"""
    # Get review and verify ownership of report
    review_result = await session.execute(
        select(StrainReview).where(StrainReview.id == review_id)
    )
    review = review_result.scalars().first()

    if not review:
        raise HTTPException(404, "Review not found")

    # Verify current user owns the report
    report_result = await session.execute(
        select(PublishedReport).where(PublishedReport.id == review.published_report_id)
    )
    report = report_result.scalars().first()

    if not report or report.user_id != current_user.id:
        raise HTTPException(403, "Not authorized to respond to this review")

    # Check if response already exists
    existing_result = await session.execute(
        select(ReviewResponse).where(ReviewResponse.review_id == review_id)
    )
    existing_response = existing_result.scalars().first()

    if existing_response:
        # Update existing response
        existing_response.response_text = response_data.response_text
        existing_response.updated_at = datetime.utcnow()
        response = existing_response
    else:
        # Create new response
        response = ReviewResponse(
            review_id=review_id,
            grower_id=current_user.id,
            **response_data.model_dump()
        )
        session.add(response)

    await session.commit()
    await session.refresh(response)

    grower_name = f"{current_user.first_name} {current_user.last_name}".strip() or current_user.email

    return ReviewResponseRead(
        id=response.id,
        review_id=response.review_id,
        grower_id=response.grower_id,
        response_text=response.response_text,
        created_at=response.created_at,
        updated_at=response.updated_at,
        grower_name=grower_name
    )


@router.delete("/reviews/{review_id}/response")
async def delete_response(
    review_id: int,
    current_user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Delete grower's response to a review"""
    result = await session.execute(
        select(ReviewResponse).where(ReviewResponse.review_id == review_id)
    )
    response = result.scalars().first()

    if not response or response.grower_id != current_user.id:
        raise HTTPException(404, "Response not found")

    await session.delete(response)
    await session.commit()

    return {"message": "Response deleted"}


# ===== ADMIN SETTINGS =====

@router.get("/admin/settings", response_model=List[AdminSettingRead])
async def get_admin_settings(
    current_user: User = Depends(require_superuser),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get all admin settings (superuser only)"""
    result = await session.execute(select(AdminSetting))
    return result.scalars().all()


@router.put("/admin/settings/{setting_key}", response_model=AdminSettingRead)
async def update_admin_setting(
    setting_key: str,
    setting_data: AdminSettingUpdate,
    current_user: User = Depends(require_superuser),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update an admin setting value (superuser only)"""
    result = await session.execute(
        select(AdminSetting).where(AdminSetting.setting_key == setting_key)
    )
    setting = result.scalars().first()

    if not setting:
        raise HTTPException(404, "Setting not found")

    setting.setting_value = setting_data.setting_value
    setting.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(setting)

    return setting
