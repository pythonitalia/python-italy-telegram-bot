"""PostgreSQL implementation of the repository using psycopg async pool."""

from psycopg_pool import AsyncConnectionPool

from .base import AsyncRepository
from .models import Chat, KnownUser


class PostgresRepository(AsyncRepository):
    """PostgreSQL repository using psycopg async connection pool."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def add_pending_verification(self, user_id: int, chat_id: int) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO pending_verifications (user_id, chat_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, chat_id) DO NOTHING
                """,
                (user_id, chat_id),
            )

    async def get_pending_chats(self, user_id: int) -> list[int]:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT chat_id FROM pending_verifications WHERE user_id = %s",
                    (user_id,),
                )
                rows = await cur.fetchall()
                return [row[0] for row in rows]

    async def remove_pending(self, user_id: int, chat_id: int) -> bool:
        async with self._pool.connection() as conn:
            result = await conn.execute(
                "DELETE FROM pending_verifications WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id),
            )
            return result.rowcount > 0

    async def is_user_verified(self, user_id: int, chat_id: int) -> bool:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT 1 FROM verified_users WHERE user_id = %s AND chat_id = %s",
                    (user_id, chat_id),
                )
                return await cur.fetchone() is not None

    async def mark_user_verified(self, user_id: int, chat_id: int) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO verified_users (user_id, chat_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, chat_id) DO NOTHING
                """,
                (user_id, chat_id),
            )

    async def get_banned_users(self, chat_id: int) -> list[int]:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id FROM bans WHERE chat_id = %s",
                    (chat_id,),
                )
                rows = await cur.fetchall()
                return [row[0] for row in rows]

    async def add_ban(
        self,
        user_id: int,
        chat_id: int,
        admin_id: int,
        reason: str | None = None,
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO bans (user_id, chat_id, admin_id, reason)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, chat_id)
                DO UPDATE SET admin_id = EXCLUDED.admin_id,
                              reason = EXCLUDED.reason,
                              created_at = NOW()
                """,
                (user_id, chat_id, admin_id, reason),
            )

    async def remove_ban(self, user_id: int, chat_id: int) -> bool:
        async with self._pool.connection() as conn:
            result = await conn.execute(
                "DELETE FROM bans WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id),
            )
            return result.rowcount > 0

    async def get_muted_users(self, chat_id: int) -> list[int]:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT user_id FROM mutes
                    WHERE chat_id = %s AND (until_ts IS NULL OR until_ts > NOW())
                    """,
                    (chat_id,),
                )
                rows = await cur.fetchall()
                return [row[0] for row in rows]

    async def add_mute(
        self,
        user_id: int,
        chat_id: int,
        admin_id: int,
        reason: str | None = None,
        until: int | None = None,
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO mutes (user_id, chat_id, admin_id, reason, until_ts)
                VALUES (%s, %s, %s, %s, TO_TIMESTAMP(%s))
                ON CONFLICT (user_id, chat_id)
                DO UPDATE SET admin_id = EXCLUDED.admin_id,
                              reason = EXCLUDED.reason,
                              until_ts = EXCLUDED.until_ts,
                              created_at = NOW()
                """,
                (user_id, chat_id, admin_id, reason, until),
            )

    async def remove_mute(self, user_id: int, chat_id: int) -> bool:
        async with self._pool.connection() as conn:
            result = await conn.execute(
                "DELETE FROM mutes WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id),
            )
            return result.rowcount > 0

    async def add_report(
        self,
        reporter_id: int,
        reported_user_id: int,
        chat_id: int,
        message_id: int | None = None,
        reason: str | None = None,
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO reports (reporter_id, reported_user_id, chat_id, message_id, reason)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (reporter_id, reported_user_id, chat_id, message_id, reason),
            )

    async def get_welcome_message(self, chat_id: int) -> str | None:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT welcome_message FROM group_settings WHERE chat_id = %s",
                    (chat_id,),
                )
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_welcome_message(self, chat_id: int, message: str | None) -> None:
        async with self._pool.connection() as conn:
            if message is None:
                await conn.execute(
                    "DELETE FROM group_settings WHERE chat_id = %s",
                    (chat_id,),
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO group_settings (chat_id, welcome_message, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (chat_id)
                    DO UPDATE SET welcome_message = EXCLUDED.welcome_message,
                                  updated_at = NOW()
                    """,
                    (chat_id, message),
                )

    async def is_globally_verified(self, user_id: int) -> bool:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT 1 FROM globally_verified_users WHERE user_id = %s",
                    (user_id,),
                )
                return await cur.fetchone() is not None

    async def mark_globally_verified(self, user_id: int) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO globally_verified_users (user_id, verified_at)
                VALUES (%s, NOW())
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id,),
            )

    async def register_chat(self, chat_id: int, title: str | None = None) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO bot_chats (chat_id, title)
                VALUES (%s, %s)
                ON CONFLICT (chat_id) DO UPDATE SET title = EXCLUDED.title
                """,
                (chat_id, title),
            )

    async def get_all_chats(self) -> list[int]:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT chat_id FROM bot_chats")
                rows = await cur.fetchall()
                return [row[0] for row in rows]

    async def get_all_chats_with_titles(self) -> list[Chat]:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT chat_id, title FROM bot_chats ORDER BY chat_id"
                )
                rows = await cur.fetchall()
                return [Chat(chat_id=row[0], title=row[1]) for row in rows]

    async def find_chats_by_title(self, query: str) -> list[Chat]:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT chat_id, title FROM bot_chats WHERE title ILIKE %s",
                    (f"%{query}%",),
                )
                rows = await cur.fetchall()
                return [Chat(chat_id=row[0], title=row[1]) for row in rows]

    async def add_global_ban(
        self,
        user_id: int,
        admin_id: int,
        reason: str | None = None,
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO global_bans (user_id, admin_id, reason)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET admin_id = EXCLUDED.admin_id,
                              reason = EXCLUDED.reason,
                              created_at = NOW()
                """,
                (user_id, admin_id, reason),
            )

    async def remove_global_ban(self, user_id: int) -> bool:
        async with self._pool.connection() as conn:
            result = await conn.execute(
                "DELETE FROM global_bans WHERE user_id = %s",
                (user_id,),
            )
            return result.rowcount > 0

    async def is_globally_banned(self, user_id: int) -> bool:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT 1 FROM global_bans WHERE user_id = %s",
                    (user_id,),
                )
                return await cur.fetchone() is not None

    # -- Known users --

    async def upsert_known_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO known_users (user_id, username, first_name, last_name, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (user_id)
                DO UPDATE SET username = EXCLUDED.username,
                              first_name = EXCLUDED.first_name,
                              last_name = EXCLUDED.last_name,
                              updated_at = NOW()
                """,
                (user_id, username, first_name, last_name),
            )

    async def get_known_user(self, user_id: int) -> KnownUser | None:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, username, first_name, last_name, updated_at "
                    "FROM known_users WHERE user_id = %s",
                    (user_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                return KnownUser(
                    user_id=row[0],
                    username=row[1],
                    first_name=row[2],
                    last_name=row[3],
                    updated_at=row[4],
                )

    async def get_known_user_by_username(self, username: str) -> KnownUser | None:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, username, first_name, last_name, updated_at "
                    "FROM known_users WHERE LOWER(username) = LOWER(%s)",
                    (username,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                return KnownUser(
                    user_id=row[0],
                    username=row[1],
                    first_name=row[2],
                    last_name=row[3],
                    updated_at=row[4],
                )

    # -- Welcomed users --

    async def has_been_welcomed(self, user_id: int, chat_id: int) -> bool:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT 1 FROM welcomed_users WHERE user_id = %s AND chat_id = %s",
                    (user_id, chat_id),
                )
                return await cur.fetchone() is not None

    async def mark_welcomed(self, user_id: int, chat_id: int) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO welcomed_users (user_id, chat_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, chat_id) DO NOTHING
                """,
                (user_id, chat_id),
            )

    # -- Welcome delay --

    async def get_welcome_delay(self, chat_id: int) -> int | None:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT welcome_delay_minutes FROM group_settings WHERE chat_id = %s",
                    (chat_id,),
                )
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_welcome_delay(self, chat_id: int, minutes: int | None) -> None:
        async with self._pool.connection() as conn:
            if minutes is None:
                await conn.execute(
                    """
                    UPDATE group_settings SET welcome_delay_minutes = NULL, updated_at = NOW()
                    WHERE chat_id = %s
                    """,
                    (chat_id,),
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO group_settings (chat_id, welcome_delay_minutes, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (chat_id)
                    DO UPDATE SET welcome_delay_minutes = EXCLUDED.welcome_delay_minutes,
                                  updated_at = NOW()
                    """,
                    (chat_id, minutes),
                )

    # -- Welcome message tracking (ban-by-reply) --

    async def store_welcome_message(
        self, chat_id: int, message_id: int, user_id: int
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO welcome_messages (chat_id, message_id, user_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (chat_id, message_id)
                DO UPDATE SET user_id = EXCLUDED.user_id
                """,
                (chat_id, message_id, user_id),
            )

    async def get_welcome_message_user(
        self, chat_id: int, message_id: int
    ) -> int | None:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id FROM welcome_messages "
                    "WHERE chat_id = %s AND message_id = %s",
                    (chat_id, message_id),
                )
                row = await cur.fetchone()
                return row[0] if row else None

    async def delete_welcome_message(self, chat_id: int, message_id: int) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "DELETE FROM welcome_messages WHERE chat_id = %s AND message_id = %s",
                (chat_id, message_id),
            )

    async def close(self) -> None:
        await self._pool.close()
