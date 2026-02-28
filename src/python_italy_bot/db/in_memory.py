"""In-memory implementation of the repository (no persistent DB)."""

from datetime import datetime, timezone

from .base import AsyncRepository
from .models import Ban, Chat, KnownUser, Mute, Report


class InMemoryRepository(AsyncRepository):
    """In-memory repository for development and testing."""

    def __init__(self) -> None:
        self._verified: set[tuple[int, int]] = set()
        self._pending: set[tuple[int, int]] = set()
        self._bans: list[Ban] = []
        self._mutes: list[Mute] = []
        self._reports: list[Report] = []
        self._welcome_messages: dict[int, str] = {}
        self._globally_verified: set[int] = set()
        self._bot_chats: dict[int, str | None] = {}
        self._global_bans: dict[int, tuple[int, str | None]] = {}
        self._known_users: dict[int, KnownUser] = {}
        self._username_to_user_id: dict[str, int] = {}
        self._welcomed: set[tuple[int, int]] = set()
        self._welcome_delays: dict[int, int] = {}
        self._welcome_message_map: dict[tuple[int, int], int] = {}

    async def add_pending_verification(self, user_id: int, chat_id: int) -> None:
        self._pending.add((user_id, chat_id))

    async def get_pending_chats(self, user_id: int) -> list[int]:
        return [c for u, c in self._pending if u == user_id]

    async def remove_pending(self, user_id: int, chat_id: int) -> bool:
        key = (user_id, chat_id)
        if key in self._pending:
            self._pending.discard(key)
            return True
        return False

    async def is_user_verified(self, user_id: int, chat_id: int) -> bool:
        return (user_id, chat_id) in self._verified

    async def mark_user_verified(self, user_id: int, chat_id: int) -> None:
        self._verified.add((user_id, chat_id))

    async def get_banned_users(self, chat_id: int) -> list[int]:
        return [b.user_id for b in self._bans if b.chat_id == chat_id]

    async def add_ban(
        self,
        user_id: int,
        chat_id: int,
        admin_id: int,
        reason: str | None = None,
    ) -> None:
        self._bans.append(
            Ban(
                user_id=user_id,
                chat_id=chat_id,
                admin_id=admin_id,
                reason=reason,
                created_at=datetime.now(timezone.utc),
            )
        )

    async def remove_ban(self, user_id: int, chat_id: int) -> bool:
        before = len(self._bans)
        self._bans = [
            b for b in self._bans if not (b.user_id == user_id and b.chat_id == chat_id)
        ]
        return len(self._bans) < before

    async def get_muted_users(self, chat_id: int) -> list[int]:
        now = datetime.now(timezone.utc)
        return [
            m.user_id
            for m in self._mutes
            if m.chat_id == chat_id and (m.until is None or m.until > now)
        ]

    async def add_mute(
        self,
        user_id: int,
        chat_id: int,
        admin_id: int,
        reason: str | None = None,
        until: int | None = None,
    ) -> None:
        until_dt = datetime.fromtimestamp(until, tz=timezone.utc) if until else None
        self._mutes.append(
            Mute(
                user_id=user_id,
                chat_id=chat_id,
                admin_id=admin_id,
                reason=reason,
                until=until_dt,
                created_at=datetime.now(timezone.utc),
            )
        )

    async def remove_mute(self, user_id: int, chat_id: int) -> bool:
        before = len(self._mutes)
        self._mutes = [
            m
            for m in self._mutes
            if not (m.user_id == user_id and m.chat_id == chat_id)
        ]
        return len(self._mutes) < before

    async def add_report(
        self,
        reporter_id: int,
        reported_user_id: int,
        chat_id: int,
        message_id: int | None = None,
        reason: str | None = None,
    ) -> None:
        self._reports.append(
            Report(
                reporter_id=reporter_id,
                reported_user_id=reported_user_id,
                chat_id=chat_id,
                message_id=message_id,
                reason=reason,
                created_at=datetime.now(timezone.utc),
            )
        )

    async def get_welcome_message(self, chat_id: int) -> str | None:
        return self._welcome_messages.get(chat_id)

    async def set_welcome_message(self, chat_id: int, message: str | None) -> None:
        if message is None:
            self._welcome_messages.pop(chat_id, None)
        else:
            self._welcome_messages[chat_id] = message

    async def is_globally_verified(self, user_id: int) -> bool:
        return user_id in self._globally_verified

    async def mark_globally_verified(self, user_id: int) -> None:
        self._globally_verified.add(user_id)

    async def register_chat(self, chat_id: int, title: str | None = None) -> None:
        self._bot_chats[chat_id] = title

    async def get_all_chats(self) -> list[int]:
        return list(self._bot_chats.keys())

    async def get_all_chats_with_titles(self) -> list[Chat]:
        return [Chat(chat_id=cid, title=t) for cid, t in self._bot_chats.items()]

    async def find_chats_by_title(self, query: str) -> list[Chat]:
        query_lower = query.lower()
        return [
            Chat(chat_id=cid, title=t)
            for cid, t in self._bot_chats.items()
            if t and query_lower in t.lower()
        ]

    async def add_global_ban(
        self,
        user_id: int,
        admin_id: int,
        reason: str | None = None,
    ) -> None:
        self._global_bans[user_id] = (admin_id, reason)

    async def remove_global_ban(self, user_id: int) -> bool:
        if user_id in self._global_bans:
            del self._global_bans[user_id]
            return True
        return False

    async def is_globally_banned(self, user_id: int) -> bool:
        return user_id in self._global_bans

    # -- Known users --

    async def upsert_known_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        old = self._known_users.get(user_id)
        if old and old.username:
            self._username_to_user_id.pop(old.username.lower(), None)
        user = KnownUser(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            updated_at=datetime.now(timezone.utc),
        )
        self._known_users[user_id] = user
        if username:
            self._username_to_user_id[username.lower()] = user_id

    async def get_known_user(self, user_id: int) -> KnownUser | None:
        return self._known_users.get(user_id)

    async def get_known_user_by_username(self, username: str) -> KnownUser | None:
        uid = self._username_to_user_id.get(username.lower())
        if uid is not None:
            return self._known_users.get(uid)
        return None

    # -- Welcomed users --

    async def has_been_welcomed(self, user_id: int, chat_id: int) -> bool:
        return (user_id, chat_id) in self._welcomed

    async def mark_welcomed(self, user_id: int, chat_id: int) -> None:
        self._welcomed.add((user_id, chat_id))

    # -- Welcome delay --

    async def get_welcome_delay(self, chat_id: int) -> int | None:
        return self._welcome_delays.get(chat_id)

    async def set_welcome_delay(self, chat_id: int, minutes: int | None) -> None:
        if minutes is None:
            self._welcome_delays.pop(chat_id, None)
        else:
            self._welcome_delays[chat_id] = minutes

    # -- Welcome message tracking --

    async def store_welcome_message(
        self, chat_id: int, message_id: int, user_id: int
    ) -> None:
        self._welcome_message_map[(chat_id, message_id)] = user_id

    async def get_welcome_message_user(
        self, chat_id: int, message_id: int
    ) -> int | None:
        return self._welcome_message_map.get((chat_id, message_id))

    async def delete_welcome_message(self, chat_id: int, message_id: int) -> None:
        self._welcome_message_map.pop((chat_id, message_id), None)
