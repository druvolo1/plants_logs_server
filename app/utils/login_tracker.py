# app/utils/login_tracker.py
"""
Login tracking utilities.
"""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models import User, LoginHistory


async def record_login(
    session: AsyncSession,
    user: User,
    ip_address: str = None,
    user_agent: str = None
) -> None:
    """
    Record a user login event.

    Updates user's last_login timestamp and login_count,
    creates a new LoginHistory record, and maintains only
    the 10 most recent login records per user.

    Args:
        session: Database session
        user: User object
        ip_address: Client IP address (optional)
        user_agent: Client user agent string (optional)
    """
    # Update user login stats
    user.last_login = datetime.utcnow()
    user.login_count = (user.login_count or 0) + 1

    # Create new login history record
    new_login = LoginHistory(
        user_id=user.id,
        login_at=datetime.utcnow(),
        ip_address=ip_address,
        user_agent=user_agent
    )
    session.add(new_login)

    # Get count of existing login history records for this user
    count_result = await session.execute(
        select(LoginHistory).where(LoginHistory.user_id == user.id)
    )
    existing_logins = count_result.scalars().all()

    # If we have more than 10 records, delete the oldest ones
    if len(existing_logins) >= 10:
        # Sort by login_at descending (newest first)
        sorted_logins = sorted(existing_logins, key=lambda x: x.login_at, reverse=True)

        # Get IDs of records to delete (everything after the 9th, since we're adding a new one)
        to_delete_ids = [login.id for login in sorted_logins[9:]]

        if to_delete_ids:
            await session.execute(
                delete(LoginHistory).where(LoginHistory.id.in_(to_delete_ids))
            )

    await session.commit()
