from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.user_settings import AfterFoodAddAction, NumberFormat


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        statement = select(User).where(User.telegram_id == telegram_id)
        return await self._session.scalar(statement)

    async def get_by_id(self, user_id: int) -> User | None:
        statement = (
            select(User)
            .where(User.id == user_id)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def update_settings(
        self,
        user_id: int,
        *,
        timezone: str | None = None,
        number_format: NumberFormat | None = None,
        after_food_add_action: AfterFoodAddAction | None = None,
        confirm_deletions: bool | None = None,
    ) -> User | None:
        values: dict[str, object] = {}
        if timezone is not None:
            values["timezone"] = timezone
        if number_format is not None:
            values["number_format"] = number_format.value
        if after_food_add_action is not None:
            values["after_food_add_action"] = after_food_add_action.value
        if confirm_deletions is not None:
            values["confirm_deletions"] = confirm_deletions
        if not values:
            return await self.get_by_id(user_id)
        statement = (
            update(User)
            .where(User.id == user_id)
            .values(**values)
            .returning(User)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def create_or_get(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
        timezone: str,
    ) -> tuple[User, bool]:
        statement = (
            insert(User)
            .values(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code,
                timezone=timezone,
            )
            .on_conflict_do_nothing(index_elements=[User.telegram_id])
            .returning(User)
        )
        created_user = await self._session.scalar(statement)
        if created_user is not None:
            return created_user, True

        existing_user = await self.get_by_telegram_id(telegram_id)
        if existing_user is None:
            msg = "User conflict occurred but the existing user was not found"
            raise RuntimeError(msg)
        return existing_user, False

    @staticmethod
    def update_telegram_data(
        user: User,
        *,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
    ) -> None:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.language_code = language_code
