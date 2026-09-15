from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import MenuButtonCommands, MenuButtonWebApp, WebAppInfo

from app.config import Settings


@dataclass(frozen=True, slots=True)
class MiniAppRollout:
    enabled: bool
    public_url: str
    allowed_telegram_ids: frozenset[int]
    manage_menu_button: bool
    menu_button_text: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "MiniAppRollout":
        return cls(
            enabled=settings.miniapp_enabled,
            public_url=str(settings.miniapp_public_url).rstrip("/"),
            allowed_telegram_ids=frozenset(settings.miniapp_allowed_telegram_ids),
            manage_menu_button=settings.miniapp_manage_menu_button,
            menu_button_text=settings.miniapp_menu_button_text,
        )

    def is_available_to(self, telegram_id: int) -> bool:
        return self.enabled and (
            not self.allowed_telegram_ids or telegram_id in self.allowed_telegram_ids
        )


async def reconcile_miniapp_menu_button(
    bot: Bot,
    rollout: MiniAppRollout,
) -> None:
    if not rollout.manage_menu_button:
        return

    commands_button = MenuButtonCommands()
    if not rollout.enabled:
        await bot.set_chat_menu_button(menu_button=commands_button)
        for telegram_id in sorted(rollout.allowed_telegram_ids):
            await bot.set_chat_menu_button(
                chat_id=telegram_id,
                menu_button=commands_button,
            )
        return

    web_app_button = MenuButtonWebApp(
        text=rollout.menu_button_text,
        web_app=WebAppInfo(url=rollout.public_url),
    )
    if not rollout.allowed_telegram_ids:
        await bot.set_chat_menu_button(menu_button=web_app_button)
        return

    await bot.set_chat_menu_button(menu_button=commands_button)
    for telegram_id in sorted(rollout.allowed_telegram_ids):
        await bot.set_chat_menu_button(
            chat_id=telegram_id,
            menu_button=web_app_button,
        )
