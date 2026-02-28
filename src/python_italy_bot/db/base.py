"""Abstract repository interface for persistence."""

from abc import ABC, abstractmethod

from .models import Chat, KnownUser


class Repository(ABC):
    """Abstract interface for data persistence (sync)."""

    @abstractmethod
    def add_pending_verification(self, user_id: int, chat_id: int) -> None:
        """Record that user joined chat and needs to complete captcha."""
        ...

    @abstractmethod
    def get_pending_chats(self, user_id: int) -> list[int]:
        """Return chat IDs where user is pending verification."""
        ...

    @abstractmethod
    def remove_pending(self, user_id: int, chat_id: int) -> bool:
        """Remove pending verification. Returns True if existed."""
        ...

    @abstractmethod
    def is_user_verified(self, user_id: int, chat_id: int) -> bool:
        """Check if user has completed captcha for the given chat."""
        ...

    @abstractmethod
    def mark_user_verified(self, user_id: int, chat_id: int) -> None:
        """Mark user as verified for the given chat."""
        ...

    @abstractmethod
    def get_banned_users(self, chat_id: int) -> list[int]:
        """Return user IDs banned in the given chat."""
        ...

    @abstractmethod
    def add_ban(
        self,
        user_id: int,
        chat_id: int,
        admin_id: int,
        reason: str | None = None,
    ) -> None:
        """Record a ban."""
        ...

    @abstractmethod
    def remove_ban(self, user_id: int, chat_id: int) -> bool:
        """Remove a ban. Returns True if ban existed."""
        ...

    @abstractmethod
    def get_muted_users(self, chat_id: int) -> list[int]:
        """Return user IDs currently muted in the given chat."""
        ...

    @abstractmethod
    def add_mute(
        self,
        user_id: int,
        chat_id: int,
        admin_id: int,
        reason: str | None = None,
        until: int | None = None,
    ) -> None:
        """Record a mute. until is Unix timestamp or None for indefinite."""
        ...

    @abstractmethod
    def remove_mute(self, user_id: int, chat_id: int) -> bool:
        """Remove a mute. Returns True if mute existed."""
        ...

    @abstractmethod
    def add_report(
        self,
        reporter_id: int,
        reported_user_id: int,
        chat_id: int,
        message_id: int | None = None,
        reason: str | None = None,
    ) -> None:
        """Record a report."""
        ...

    @abstractmethod
    def get_welcome_message(self, chat_id: int) -> str | None:
        """Get custom welcome message for a chat."""
        ...

    @abstractmethod
    def set_welcome_message(self, chat_id: int, message: str | None) -> None:
        """Set custom welcome message for a chat. Pass None to remove."""
        ...

    @abstractmethod
    def is_globally_verified(self, user_id: int) -> bool:
        """Check if user is globally verified across all chats."""
        ...

    @abstractmethod
    def mark_globally_verified(self, user_id: int) -> None:
        """Mark user as globally verified."""
        ...

    @abstractmethod
    def register_chat(self, chat_id: int, title: str | None = None) -> None:
        """Track a chat where the bot is active."""
        ...

    @abstractmethod
    def get_all_chats(self) -> list[int]:
        """Get all tracked chat IDs."""
        ...

    @abstractmethod
    def get_all_chats_with_titles(self) -> list[Chat]:
        """Get all tracked chats with their titles."""
        ...

    @abstractmethod
    def find_chats_by_title(self, query: str) -> list[Chat]:
        """Find tracked chats whose title contains the query (case-insensitive)."""
        ...

    @abstractmethod
    def add_global_ban(
        self,
        user_id: int,
        admin_id: int,
        reason: str | None = None,
    ) -> None:
        """Add a global ban for a user."""
        ...

    @abstractmethod
    def remove_global_ban(self, user_id: int) -> bool:
        """Remove a global ban. Returns True if existed."""
        ...

    @abstractmethod
    def is_globally_banned(self, user_id: int) -> bool:
        """Check if user is globally banned."""
        ...

    # -- Known users (user tracking) --

    @abstractmethod
    def upsert_known_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        """Insert or update a known user's info."""
        ...

    @abstractmethod
    def get_known_user(self, user_id: int) -> KnownUser | None:
        """Get a known user by ID."""
        ...

    @abstractmethod
    def get_known_user_by_username(self, username: str) -> KnownUser | None:
        """Get a known user by username (case-insensitive)."""
        ...

    # -- Welcomed users (welcome-once-per-group) --

    @abstractmethod
    def has_been_welcomed(self, user_id: int, chat_id: int) -> bool:
        """Check if user has already been welcomed in this chat."""
        ...

    @abstractmethod
    def mark_welcomed(self, user_id: int, chat_id: int) -> None:
        """Mark user as having been welcomed in this chat."""
        ...

    # -- Welcome delay --

    @abstractmethod
    def get_welcome_delay(self, chat_id: int) -> int | None:
        """Get welcome message auto-delete delay in minutes for a chat."""
        ...

    @abstractmethod
    def set_welcome_delay(self, chat_id: int, minutes: int | None) -> None:
        """Set welcome message auto-delete delay. None to reset to default."""
        ...

    # -- Welcome message tracking (ban-by-reply) --

    @abstractmethod
    def store_welcome_message(
        self, chat_id: int, message_id: int, user_id: int
    ) -> None:
        """Store mapping from a welcome message to the user who triggered it."""
        ...

    @abstractmethod
    def get_welcome_message_user(self, chat_id: int, message_id: int) -> int | None:
        """Get the user_id associated with a welcome message, or None."""
        ...

    @abstractmethod
    def delete_welcome_message(self, chat_id: int, message_id: int) -> None:
        """Remove a welcome message mapping."""
        ...


class AsyncRepository(ABC):
    """Abstract interface for data persistence (async)."""

    @abstractmethod
    async def add_pending_verification(self, user_id: int, chat_id: int) -> None:
        """Record that user joined chat and needs to complete captcha."""
        ...

    @abstractmethod
    async def get_pending_chats(self, user_id: int) -> list[int]:
        """Return chat IDs where user is pending verification."""
        ...

    @abstractmethod
    async def remove_pending(self, user_id: int, chat_id: int) -> bool:
        """Remove pending verification. Returns True if existed."""
        ...

    @abstractmethod
    async def is_user_verified(self, user_id: int, chat_id: int) -> bool:
        """Check if user has completed captcha for the given chat."""
        ...

    @abstractmethod
    async def mark_user_verified(self, user_id: int, chat_id: int) -> None:
        """Mark user as verified for the given chat."""
        ...

    @abstractmethod
    async def get_banned_users(self, chat_id: int) -> list[int]:
        """Return user IDs banned in the given chat."""
        ...

    @abstractmethod
    async def add_ban(
        self,
        user_id: int,
        chat_id: int,
        admin_id: int,
        reason: str | None = None,
    ) -> None:
        """Record a ban."""
        ...

    @abstractmethod
    async def remove_ban(self, user_id: int, chat_id: int) -> bool:
        """Remove a ban. Returns True if ban existed."""
        ...

    @abstractmethod
    async def get_muted_users(self, chat_id: int) -> list[int]:
        """Return user IDs currently muted in the given chat."""
        ...

    @abstractmethod
    async def add_mute(
        self,
        user_id: int,
        chat_id: int,
        admin_id: int,
        reason: str | None = None,
        until: int | None = None,
    ) -> None:
        """Record a mute. until is Unix timestamp or None for indefinite."""
        ...

    @abstractmethod
    async def remove_mute(self, user_id: int, chat_id: int) -> bool:
        """Remove a mute. Returns True if mute existed."""
        ...

    @abstractmethod
    async def add_report(
        self,
        reporter_id: int,
        reported_user_id: int,
        chat_id: int,
        message_id: int | None = None,
        reason: str | None = None,
    ) -> None:
        """Record a report."""
        ...

    @abstractmethod
    async def get_welcome_message(self, chat_id: int) -> str | None:
        """Get custom welcome message for a chat."""
        ...

    @abstractmethod
    async def set_welcome_message(self, chat_id: int, message: str | None) -> None:
        """Set custom welcome message for a chat. Pass None to remove."""
        ...

    @abstractmethod
    async def is_globally_verified(self, user_id: int) -> bool:
        """Check if user is globally verified across all chats."""
        ...

    @abstractmethod
    async def mark_globally_verified(self, user_id: int) -> None:
        """Mark user as globally verified."""
        ...

    @abstractmethod
    async def register_chat(self, chat_id: int, title: str | None = None) -> None:
        """Track a chat where the bot is active."""
        ...

    @abstractmethod
    async def get_all_chats(self) -> list[int]:
        """Get all tracked chat IDs."""
        ...

    @abstractmethod
    async def get_all_chats_with_titles(self) -> list[Chat]:
        """Get all tracked chats with their titles."""
        ...

    @abstractmethod
    async def find_chats_by_title(self, query: str) -> list[Chat]:
        """Find tracked chats whose title contains the query (case-insensitive)."""
        ...

    @abstractmethod
    async def add_global_ban(
        self,
        user_id: int,
        admin_id: int,
        reason: str | None = None,
    ) -> None:
        """Add a global ban for a user."""
        ...

    @abstractmethod
    async def remove_global_ban(self, user_id: int) -> bool:
        """Remove a global ban. Returns True if existed."""
        ...

    @abstractmethod
    async def is_globally_banned(self, user_id: int) -> bool:
        """Check if user is globally banned."""
        ...

    # -- Known users (user tracking) --

    @abstractmethod
    async def upsert_known_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        """Insert or update a known user's info."""
        ...

    @abstractmethod
    async def get_known_user(self, user_id: int) -> KnownUser | None:
        """Get a known user by ID."""
        ...

    @abstractmethod
    async def get_known_user_by_username(self, username: str) -> KnownUser | None:
        """Get a known user by username (case-insensitive)."""
        ...

    # -- Welcomed users (welcome-once-per-group) --

    @abstractmethod
    async def has_been_welcomed(self, user_id: int, chat_id: int) -> bool:
        """Check if user has already been welcomed in this chat."""
        ...

    @abstractmethod
    async def mark_welcomed(self, user_id: int, chat_id: int) -> None:
        """Mark user as having been welcomed in this chat."""
        ...

    # -- Welcome delay --

    @abstractmethod
    async def get_welcome_delay(self, chat_id: int) -> int | None:
        """Get welcome message auto-delete delay in minutes for a chat."""
        ...

    @abstractmethod
    async def set_welcome_delay(self, chat_id: int, minutes: int | None) -> None:
        """Set welcome message auto-delete delay. None to reset to default."""
        ...

    # -- Welcome message tracking (ban-by-reply) --

    @abstractmethod
    async def store_welcome_message(
        self, chat_id: int, message_id: int, user_id: int
    ) -> None:
        """Store mapping from a welcome message to the user who triggered it."""
        ...

    @abstractmethod
    async def get_welcome_message_user(
        self, chat_id: int, message_id: int
    ) -> int | None:
        """Get the user_id associated with a welcome message, or None."""
        ...

    @abstractmethod
    async def delete_welcome_message(self, chat_id: int, message_id: int) -> None:
        """Remove a welcome message mapping."""
        ...

    async def close(self) -> None:
        """Close any resources (override if needed)."""
        pass
