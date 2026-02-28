"""Captcha verification logic (file + secret command flow)."""

import re
from pathlib import Path

from telegram import (
    Chat,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    User,
)

from .. import strings
from ..db.base import AsyncRepository

BUTTON_URL_PATTERN = re.compile(r"\[([^\]]+)\]\(buttonurl://([^)]+)\)")


class CaptchaService:
    """Handles welcome captcha: restrict new members until they send secret command in DM."""

    def __init__(
        self,
        repository: AsyncRepository,
        secret_command: str,
        file_path: str,
        rules_url: str | None = None,
    ) -> None:
        self._repo = repository
        self._secret_command = secret_command.strip().lower()
        self._file_path = Path(file_path)
        self._rules_url = rules_url

    def _matches_secret(self, text: str) -> bool:
        return text.strip().lower() == self._secret_command

    def get_default_welcome_template(self, bot_username: str) -> str:
        """Return the default welcome message template with placeholders."""
        return strings.get_default_welcome_template(bot_username)

    def format_welcome_message(
        self, template: str, user: User, chat: Chat, bot_username: str
    ) -> str:
        """Substitute placeholders in the welcome message template."""
        username = f"@{user.username}" if user.username else user.full_name
        replacements = {
            "{username}": username,
            "{chatname}": chat.title or "this group",
        }
        result = template
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, value)
        return result

    def parse_button_urls(self, text: str) -> tuple[str, InlineKeyboardMarkup | None]:
        """Extract buttonurl:// patterns and build InlineKeyboardMarkup.

        Returns (clean_text, keyboard) where clean_text has button syntax removed.
        Multiple buttons on the same line become the same row.
        """
        lines = text.split("\n")
        keyboard_rows: list[list[InlineKeyboardButton]] = []
        clean_lines: list[str] = []

        for line in lines:
            matches = list(BUTTON_URL_PATTERN.finditer(line))
            if matches:
                row = [
                    InlineKeyboardButton(text=m.group(1), url=m.group(2))
                    for m in matches
                ]
                keyboard_rows.append(row)
                clean_line = BUTTON_URL_PATTERN.sub("", line).strip()
                if clean_line:
                    clean_lines.append(clean_line)
            else:
                clean_lines.append(line)

        clean_text = "\n".join(clean_lines).strip()
        keyboard = InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None
        return clean_text, keyboard

    def get_deep_link_url(self, bot_username: str) -> str:
        """Generate the deep link URL for verification."""
        return f"https://t.me/{bot_username}?start=verify"

    def get_rules_url(self) -> str | None:
        """Return the configured rules URL."""
        return self._rules_url

    def get_captcha_file_content(self) -> str | None:
        """Return the captcha file content if it exists. Path is relative to cwd."""
        path = Path(self._file_path)
        if path.is_absolute():
            full = path
        else:
            full = Path.cwd() / path
        if full.exists():
            return full.read_text(encoding="utf-8")
        return None

    def get_restricted_permissions(self) -> ChatPermissions:
        """Permissions for unverified users (can read but not send)."""
        return ChatPermissions(
            can_send_messages=False,
            can_send_audios=False,
            can_send_documents=False,
            can_send_photos=False,
            can_send_videos=False,
            can_send_video_notes=False,
            can_send_voice_notes=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
        )

    def get_full_permissions(self) -> ChatPermissions:
        """Full permissions for verified users."""
        return ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False,
        )

    def is_secret_command(self, text: str) -> bool:
        """Check if the message matches the secret command."""
        return self._matches_secret(text)

    async def get_welcome_message(self, chat_id: int) -> str | None:
        """Get custom welcome message for a chat, or None for default."""
        return await self._repo.get_welcome_message(chat_id)

    async def set_welcome_message(self, chat_id: int, message: str | None) -> None:
        """Set or remove custom welcome message for a chat."""
        await self._repo.set_welcome_message(chat_id, message)

    async def get_pending_chats(self, user_id: int) -> list[int]:
        """Get chats where user is pending verification."""
        return await self._repo.get_pending_chats(user_id)

    async def verify_user_globally(self, user_id: int) -> None:
        """Mark user as globally verified and remove from all pending."""
        await self._repo.mark_globally_verified(user_id)
        pending_chats = await self._repo.get_pending_chats(user_id)
        for chat_id in pending_chats:
            await self._repo.remove_pending(user_id, chat_id)

    async def add_pending(self, user_id: int, chat_id: int) -> None:
        """Record that user joined and needs verification."""
        await self._repo.add_pending_verification(user_id, chat_id)

    async def is_globally_verified(self, user_id: int) -> bool:
        """Check if user is globally verified."""
        return await self._repo.is_globally_verified(user_id)

    # -- Welcome-once-per-group --

    async def has_been_welcomed(self, user_id: int, chat_id: int) -> bool:
        """Check if user has already been welcomed in this chat."""
        return await self._repo.has_been_welcomed(user_id, chat_id)

    async def mark_welcomed(self, user_id: int, chat_id: int) -> None:
        """Mark user as having been welcomed in this chat."""
        await self._repo.mark_welcomed(user_id, chat_id)

    # -- Welcome delay --

    async def get_welcome_delay(self, chat_id: int) -> int | None:
        """Get welcome message auto-delete delay in minutes for a chat."""
        return await self._repo.get_welcome_delay(chat_id)

    async def set_welcome_delay(self, chat_id: int, minutes: int | None) -> None:
        """Set welcome message auto-delete delay. None to reset to default."""
        await self._repo.set_welcome_delay(chat_id, minutes)

    # -- Welcome message tracking (ban-by-reply) --

    async def store_welcome_message(
        self, chat_id: int, message_id: int, user_id: int
    ) -> None:
        """Persist mapping from a welcome message to the user who triggered it."""
        await self._repo.store_welcome_message(chat_id, message_id, user_id)

    async def get_welcome_message_user(
        self, chat_id: int, message_id: int
    ) -> int | None:
        """Get the user_id associated with a welcome message, or None."""
        return await self._repo.get_welcome_message_user(chat_id, message_id)

    async def delete_welcome_message(self, chat_id: int, message_id: int) -> None:
        """Remove a welcome message mapping."""
        await self._repo.delete_welcome_message(chat_id, message_id)
