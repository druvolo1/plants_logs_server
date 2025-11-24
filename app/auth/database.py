"""Custom SQLAlchemy user database."""
from typing import Dict, Any
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, OAuthAccount
from app.core.database import async_session_maker


class CustomSQLAlchemyUserDatabase(SQLAlchemyUserDatabase[User, int]):
    """Custom SQLAlchemy user database with OAuth support."""

    async def add_oauth_account(
        self, user: User, create_dict: Dict[str, Any]
    ) -> User:
        """Add OAuth account to user."""
        # Preload oauth_accounts to avoid lazy loading
        stmt = (
            select(self.user_table)
            .options(selectinload(self.user_table.oauth_accounts))
            .where(self.user_table.id == user.id)
        )
        result = await self.session.execute(stmt)
        user = result.scalars().one_or_none()
        if user is None:
            raise ValueError("User not found")

        if self.oauth_account_table is None:
            raise ValueError("No OAuth account table configured.")

        oauth_account = self.oauth_account_table(**create_dict)
        self.session.add(oauth_account)
        user.oauth_accounts.append(oauth_account)
        await self.session.commit()
        return user


async def get_db():
    """Get database session dependency."""
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_db)):
    """Get user database dependency."""
    yield CustomSQLAlchemyUserDatabase(session, User, oauth_account_table=OAuthAccount)
