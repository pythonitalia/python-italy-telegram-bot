"""Moderation handlers: ban, mute, report."""

import logging
import re

from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from .. import strings
from ..db.base import AsyncRepository
from ..services.captcha import CaptchaService
from ..services.moderation import ModerationService

logger = logging.getLogger(__name__)


async def _is_admin(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int
) -> bool:
    """Check if user is admin in the chat."""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False


def create_moderation_handlers(moderation_service: ModerationService) -> list:
    """Create ban, mute, and report handlers."""
    return [
        CommandHandler("ban", _handle_ban),
        CommandHandler("unban", _handle_unban),
        CommandHandler("mute", _handle_mute),
        CommandHandler("unmute", _handle_unmute),
        CommandHandler("report", _handle_report),
        CommandHandler("forcegroupregistration", _handle_force_group_registration),
        MessageHandler(
            (filters.TEXT | filters.CAPTION)
            & filters.ChatType.GROUPS
            & filters.Regex(r"(?i)@admin"),
            _handle_admin_mention,
        ),
    ]


async def _handle_force_group_registration(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Force registration of current chat in bot_chats table. Admin only."""
    moderation_service: ModerationService = context.bot_data["moderation_service"]
    message = update.message
    if message is None or message.from_user is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type == "private":
        await message.reply_text(strings.ONLY_IN_GROUPS)
        return

    if not await _is_admin(context, chat.id, message.from_user.id):
        await message.reply_text(strings.ONLY_ADMINS)
        return

    await moderation_service.register_chat(chat.id, chat.title)
    await message.reply_text(strings.GROUP_REGISTERED.format(chat_id=chat.id))


async def _handle_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a user globally. Usage: /ban user_id|@username [reason] or reply with /ban [reason]."""
    moderation_service: ModerationService = context.bot_data["moderation_service"]
    message = update.message
    if message is None or message.from_user is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type == "private":
        return

    if not await _is_admin(context, chat.id, message.from_user.id):
        await message.reply_text(strings.ONLY_ADMINS)
        return

    args = message.text.split(maxsplit=2)[1:] if message.text else []

    user_id: int | None = None
    reason: str | None = None
    if message.reply_to_message:
        reply = message.reply_to_message
        if reply.from_user and not reply.from_user.is_bot:
            # Replying to a regular user's message
            user_id = reply.from_user.id
        else:
            # Replying to a bot message — check welcome_message_map
            welcome_map: dict[tuple[int, int], int] = context.bot_data.get(
                "welcome_message_map", {}
            )
            user_id = welcome_map.get((chat.id, reply.message_id))
            # Fall back to database if not in memory (e.g. after bot restart)
            if user_id is None:
                captcha_service: CaptchaService = context.bot_data["captcha_service"]
                user_id = await captcha_service.get_welcome_message_user(
                    chat.id, reply.message_id
                )
        reason = " ".join(args) if args else None
    elif args:
        target = args[0]
        reason = args[1] if len(args) > 1 else None
        user_id = await _resolve_user_id(context, chat.id, target, moderation_service)

    if user_id is None:
        await message.reply_text(strings.BAN_USAGE)
        return

    chat_ids = await moderation_service.add_global_ban(
        user_id, message.from_user.id, reason
    )

    success_count = 0
    fail_count = 0
    for cid in chat_ids:
        try:
            await context.bot.ban_chat_member(cid, user_id)
            success_count += 1
        except Exception as e:
            logger.debug("Ban in chat %s failed: %s", cid, e)
            fail_count += 1

    await message.reply_text(strings.ban_success(success_count, fail_count, reason))

    # Notify admins of the ban
    await _notify_admins_of_ban(
        context=context,
        chat=chat,
        admin=message.from_user,
        banned_user_id=user_id,
        success_count=success_count,
        reason=reason,
    )


async def _handle_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unban a user globally. Usage: /unban user_id or reply to message with /unban."""
    moderation_service: ModerationService = context.bot_data["moderation_service"]
    message = update.message
    if message is None or message.from_user is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type == "private":
        return

    if not await _is_admin(context, chat.id, message.from_user.id):
        await message.reply_text(strings.ONLY_ADMINS)
        return

    args = message.text.split(maxsplit=1)[1:] if message.text else []
    user_id: int | None = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
    elif args:
        user_id = await _resolve_user_id(context, chat.id, args[0], moderation_service)

    if user_id is None:
        await message.reply_text(strings.UNBAN_USAGE)
        return

    chat_ids = await moderation_service.remove_global_ban(user_id)

    success_count = 0
    fail_count = 0
    for cid in chat_ids:
        try:
            await context.bot.unban_chat_member(cid, user_id)
            success_count += 1
        except Exception as e:
            logger.debug("Unban in chat %s failed: %s", cid, e)
            fail_count += 1

    await message.reply_text(strings.unban_success(success_count, fail_count))


async def _handle_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mute a user. Usage: /mute @username [duration_minutes] [reason]."""
    moderation_service: ModerationService = context.bot_data["moderation_service"]
    message = update.message
    if message is None or message.from_user is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type == "private":
        return

    if not await _is_admin(context, chat.id, message.from_user.id):
        await message.reply_text(strings.ONLY_ADMINS)
        return

    args = message.text.split(maxsplit=3)[1:] if message.text else []
    user_id: int | None = None
    duration: int | None = None
    reason: str | None = None

    if message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
        if args:
            if args[0].isdigit():
                duration = int(args[0])
                reason = args[1] if len(args) > 1 else None
            else:
                reason = args[0]
    elif args:
        target = args[0]
        if len(args) > 1 and args[1].isdigit():
            duration = int(args[1])
            reason = args[2] if len(args) > 2 else None
        else:
            reason = args[1] if len(args) > 1 else None
        user_id = await _resolve_user_id(context, chat.id, target, moderation_service)

    if user_id is None:
        await message.reply_text(strings.MUTE_USAGE)
    if user_id is None:
        await message.reply_text(strings.USER_NOT_FOUND)
        return

    until = None
    if duration is not None and duration > 0:
        from datetime import datetime, timezone

        until = int((datetime.now(timezone.utc).timestamp()) + duration * 60)

    try:
        await context.bot.restrict_chat_member(
            chat.id,
            user_id,
            moderation_service.get_mute_permissions(),
            until_date=until,
        )
        await moderation_service.add_mute(
            user_id,
            chat.id,
            message.from_user.id,
            reason=reason,
            until=until,
        )
        await message.reply_text(strings.mute_success(duration, reason))
    except Exception as e:
        logger.warning("Mute failed: %s", e)
        await message.reply_text(strings.MUTE_FAILED)


async def _handle_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmute a user. Usage: /unmute @username."""
    moderation_service: ModerationService = context.bot_data["moderation_service"]
    message = update.message
    if message is None or message.from_user is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type == "private":
        return

    if not await _is_admin(context, chat.id, message.from_user.id):
        await message.reply_text(strings.ONLY_ADMINS)
        return

    args = message.text.split(maxsplit=1)[1:] if message.text else []
    user_id: int | None = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
    elif args:
        user_id = await _resolve_user_id(context, chat.id, args[0], moderation_service)

    if user_id is None:
        await message.reply_text(strings.UNMUTE_USAGE)
    if user_id is None:
        await message.reply_text(strings.USER_NOT_FOUND)
        return

    from telegram import ChatPermissions

    full_perms = ChatPermissions(
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

    try:
        await context.bot.restrict_chat_member(chat.id, user_id, full_perms)
        await moderation_service.remove_mute(user_id, chat.id)
        await message.reply_text(strings.UNMUTE_SUCCESS)
    except Exception as e:
        logger.warning("Unmute failed: %s", e)
        await message.reply_text(strings.UNMUTE_FAILED)


async def _handle_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report a message or user. Usage: /report [reason] or reply to message with /report [reason]."""
    moderation_service: ModerationService = context.bot_data["moderation_service"]
    message = update.message
    if message is None or message.from_user is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type == "private":
        return

    args = message.text.split(maxsplit=1)[1:] if message.text else []
    reason = args[0] if args else None

    reported_user_id: int | None = None
    message_id: int | None = None
    reported_user = None

    if message.reply_to_message and message.reply_to_message.from_user:
        reported_user = message.reply_to_message.from_user
        reported_user_id = reported_user.id
        message_id = message.reply_to_message.message_id

    if reported_user_id is None or reported_user is None:
        await message.reply_text(strings.REPORT_USAGE)
        return

    await moderation_service.add_report(
        reporter_id=message.from_user.id,
        reported_user_id=reported_user_id,
        chat_id=chat.id,
        message_id=message_id,
        reason=reason,
    )

    await _notify_admins_of_report(
        context=context,
        chat=chat,
        reporter=message.from_user,
        reported_user=reported_user,
        message_id=message_id,
        reason=reason,
    )

    await message.reply_text(strings.REPORT_SUCCESS)
    logger.info(
        "Report: %s reported %s in chat %s",
        message.from_user.id,
        reported_user_id,
        chat.id,
    )


async def _handle_admin_mention(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle @admin mention: notify admins of intervention request (no reply needed)."""
    message = update.message
    if message is None or message.from_user is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type == "private":
        return

    text = message.text or message.caption or ""
    reason = _extract_reason_after_admin(text)

    await _notify_admins_of_admin_request(
        context=context,
        chat=chat,
        reporter=message.from_user,
        message_id=message.message_id,
        reason=reason,
    )

    await message.reply_text(strings.ADMIN_REQUEST_SUCCESS)
    logger.info(
        "Admin request: %s in chat %s",
        message.from_user.id,
        chat.id,
    )


def _extract_reason_after_admin(text: str) -> str | None:
    """Extract optional reason from text after @admin."""
    match = re.search(r"@admin\s*(.+)?", text, re.IGNORECASE | re.DOTALL)
    if match and match.group(1):
        return match.group(1).strip() or None
    return None


async def _notify_admins_of_admin_request(
    context: ContextTypes.DEFAULT_TYPE,
    chat,
    reporter,
    message_id: int,
    reason: str | None,
) -> None:
    """Send admin intervention request notification to all chat admins via private message."""
    try:
        admins = await context.bot.get_chat_administrators(chat.id)
    except Exception as e:
        logger.warning("Failed to get admins for @admin notification: %s", e)
        return

    chat_title = chat.title or "Chat"
    reporter_name = _get_user_display_name(reporter)
    message_link = _build_message_link(chat, message_id)

    report_text = f"<b>{chat_title}:</b>\n"
    report_text += f'Richiesta intervento da: <a href="tg://user?id={reporter.id}">{reporter_name}</a> ({reporter.id})\n'
    if message_link:
        report_text += f'Link: <a href="{message_link}">qui</a>\n'
    if reason:
        report_text += f"Messaggio: {reason}"

    for admin in admins:
        if admin.user.is_bot:
            continue
        try:
            await context.bot.send_message(
                chat_id=admin.user.id,
                text=report_text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug(
                "Could not send @admin request to admin %s: %s",
                admin.user.id,
                e,
            )


def _get_user_display_name(user) -> str:
    """Get display name for a user (full name or username)."""
    if user.first_name:
        name = user.first_name
        if user.last_name:
            name += f" {user.last_name}"
        return name
    return user.username or str(user.id)


def _build_message_link(chat, message_id: int | None) -> str | None:
    """Build a link to a message in a chat."""
    if message_id is None:
        return None
    if chat.username:
        return f"https://t.me/{chat.username}/{message_id}"
    chat_id_str = str(chat.id)
    if chat_id_str.startswith("-100"):
        chat_id_str = chat_id_str[4:]
    return f"https://t.me/c/{chat_id_str}/{message_id}"


async def _notify_admins_of_report(
    context: ContextTypes.DEFAULT_TYPE,
    chat,
    reporter,
    reported_user,
    message_id: int | None,
    reason: str | None,
) -> None:
    """Send report notification to all chat admins via private message."""
    try:
        admins = await context.bot.get_chat_administrators(chat.id)
    except Exception as e:
        logger.warning("Failed to get admins for report notification: %s", e)
        return

    chat_title = chat.title or "Chat"
    reporter_name = _get_user_display_name(reporter)
    reported_name = _get_user_display_name(reported_user)
    message_link = _build_message_link(chat, message_id)

    report_text = f"<b>{chat_title}:</b>\n"
    report_text += f'Reported user: <a href="tg://user?id={reported_user.id}">{reported_name}</a> ({reported_user.id})\n'
    report_text += f'Reported by: <a href="tg://user?id={reporter.id}">{reporter_name}</a> ({reporter.id})\n'
    if message_link:
        report_text += f'Link: <a href="{message_link}">qui</a>\n'
    if reason:
        report_text += f"Reason: {reason}"

    for admin in admins:
        if admin.user.is_bot:
            continue
        try:
            await context.bot.send_message(
                chat_id=admin.user.id,
                text=report_text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug("Could not send report to admin %s: %s", admin.user.id, e)


async def _notify_admins_of_ban(
    context: ContextTypes.DEFAULT_TYPE,
    chat,
    admin,
    banned_user_id: int,
    success_count: int,
    reason: str | None,
) -> None:
    """Send ban notification to all chat admins via private message."""
    try:
        chat_admins = await context.bot.get_chat_administrators(chat.id)
    except Exception as e:
        logger.warning("Failed to get admins for ban notification: %s", e)
        return

    chat_title = chat.title or "Chat"
    admin_name = _get_user_display_name(admin)

    # Try to get banned user display name from known_users
    banned_name = str(banned_user_id)
    repository: AsyncRepository | None = context.bot_data.get("repository")
    if repository is not None:
        known_user = await repository.get_known_user(banned_user_id)
        if known_user is not None:
            if known_user.first_name:
                banned_name = known_user.first_name
                if known_user.last_name:
                    banned_name += f" {known_user.last_name}"
            elif known_user.username:
                banned_name = f"@{known_user.username}"

    notification = strings.ban_notification(
        chat_title=chat_title,
        banned_name=banned_name,
        banned_id=banned_user_id,
        admin_name=admin_name,
        admin_id=admin.id,
        success_count=success_count,
        reason=reason,
    )

    for member in chat_admins:
        if member.user.is_bot:
            continue
        # Don't notify the admin who performed the ban
        if member.user.id == admin.id:
            continue
        try:
            await context.bot.send_message(
                chat_id=member.user.id,
                text=notification,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug(
                "Could not send ban notification to admin %s: %s",
                member.user.id,
                e,
            )


async def _resolve_user_id(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    target: str,
    moderation_service: ModerationService | None = None,
) -> int | None:
    """Resolve @username or user_id to numeric user_id.

    Resolution order for @username:
    1. Check chat administrators (works for admins only).
    2. Fall back to known_users table (any user the bot has seen).
    """
    target = target.strip()
    if target.startswith("@"):
        username_lower = target.lstrip("@").lower()
        # Try admins first
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            for admin in admins:
                if (
                    admin.user.username
                    and admin.user.username.lower() == username_lower
                ):
                    return admin.user.id
        except Exception:
            pass
        # Fall back to known_users table
        if moderation_service is not None:
            known = await moderation_service.get_known_user_by_username(username_lower)
            if known is not None:
                return known.user_id
        # Try Telegram API as last resort
        try:
            resolved_chat = await context.bot.get_chat(f"@{username_lower}")
            if resolved_chat.id:
                return resolved_chat.id
        except Exception:
            pass
        return None
    if re.match(r"^-?\d+$", target):
        return int(target)
    return None
