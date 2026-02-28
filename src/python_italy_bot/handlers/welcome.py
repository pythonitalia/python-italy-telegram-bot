"""Welcome and captcha handlers for new members."""

import logging

from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .. import strings
from ..db.base import AsyncRepository
from ..services.captcha import CaptchaService
from ..services.moderation import ModerationService
from .utils import track_user

logger = logging.getLogger(__name__)

DEFAULT_WELCOME_DELAY_MINUTES = 5


def create_welcome_handlers(captcha_service: CaptchaService) -> list:
    """Create welcome and captcha handlers."""
    return [
        ChatMemberHandler(
            _handle_new_member,
            ChatMemberHandler.CHAT_MEMBER,
        ),
        CommandHandler("start", _handle_start),
        MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            _handle_private_message,
        ),
    ]


async def _delete_welcome_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback: delete a welcome message after the configured delay."""
    job = context.job
    if job is None or job.data is None:
        return
    data: tuple[int, int] = job.data  # type: ignore[assignment]
    chat_id, message_id = data
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.debug(
            "Could not delete welcome message %s in chat %s: %s", message_id, chat_id, e
        )

    # Clean up in-memory mapping
    welcome_map: dict[tuple[int, int], int] = context.bot_data.get(
        "welcome_message_map", {}
    )
    welcome_map.pop((chat_id, message_id), None)

    # Clean up database mapping
    captcha_service: CaptchaService | None = context.bot_data.get("captcha_service")
    if captcha_service is not None:
        try:
            await captcha_service.delete_welcome_message(chat_id, message_id)
        except Exception as e:
            logger.debug("Could not delete welcome message mapping from DB: %s", e)


async def _handle_new_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle new chat members: restrict and send welcome with captcha instructions."""
    captcha_service: CaptchaService = context.bot_data["captcha_service"]
    moderation_service: ModerationService = context.bot_data["moderation_service"]
    repository: AsyncRepository = context.bot_data["repository"]
    result = update.chat_member
    if result is None:
        return

    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status if result.old_chat_member else None

    if new_status not in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED):
        return
    if old_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    ):
        return

    user = result.new_chat_member.user
    chat = update.effective_chat
    if user is None or chat is None:
        return

    await moderation_service.register_chat(chat.id, chat.title)

    # Track the new member explicitly: middleware tracks effective_user (the admin
    # when someone is added by an admin), but we need to track the joined member.
    await track_user(repository, user)

    if user.is_bot:
        return

    if await moderation_service.is_globally_banned(user.id):
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            logger.info("Kicked globally banned user %s from chat %s", user.id, chat.id)
        except Exception as e:
            logger.warning("Failed to kick globally banned user %s: %s", user.id, e)
        return

    if await captcha_service.is_globally_verified(user.id):
        return

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=captcha_service.get_restricted_permissions(),
        )
    except Exception as e:
        logger.warning("Could not restrict user %s in chat %s: %s", user.id, chat.id, e)
        return

    await captcha_service.add_pending(user.id, chat.id)

    # Skip welcome if user was already welcomed in this chat
    if await captcha_service.has_been_welcomed(user.id, chat.id):
        return

    bot_me = await context.bot.get_me()
    bot_username = bot_me.username or "bot"

    custom_template = await captcha_service.get_welcome_message(chat.id)
    if custom_template:
        template = custom_template
    else:
        template = captcha_service.get_default_welcome_template(bot_username)

    formatted = captcha_service.format_welcome_message(
        template, user, chat, bot_username
    )
    text, keyboard = captcha_service.parse_button_urls(formatted)

    try:
        sent = await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning("Could not send welcome to chat %s: %s", chat.id, e)
        return

    # Mark user as welcomed in this chat
    await captcha_service.mark_welcomed(user.id, chat.id)

    # Store welcome message -> user mapping for ban-by-reply
    welcome_map = context.bot_data.setdefault("welcome_message_map", {})
    welcome_map[(chat.id, sent.message_id)] = user.id

    # Persist to database so the mapping survives bot restarts
    try:
        await captcha_service.store_welcome_message(chat.id, sent.message_id, user.id)
    except Exception as e:
        logger.warning("Could not persist welcome message mapping: %s", e)

    # Schedule auto-deletion of the welcome message
    delay_minutes = await captcha_service.get_welcome_delay(chat.id)
    if delay_minutes is None:
        delay_minutes = DEFAULT_WELCOME_DELAY_MINUTES
    if delay_minutes > 0 and context.job_queue is not None:
        context.job_queue.run_once(
            _delete_welcome_message,
            when=delay_minutes * 60,
            data=(chat.id, sent.message_id),
            name=f"del_welcome_{chat.id}_{sent.message_id}",
        )


async def _handle_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /start command, including deep link for verification."""
    captcha_service: CaptchaService = context.bot_data["captcha_service"]
    message = update.message
    if message is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type != "private":
        return

    user = update.effective_user
    if user is None:
        return

    args = context.args
    if args and args[0] == "verify":
        rules_url = captcha_service.get_rules_url()
        if rules_url:
            await message.reply_text(
                strings.VERIFY_READ_RULES_URL.format(rules_url=rules_url)
            )
        else:
            captcha_content = captcha_service.get_captcha_file_content()
            if captcha_content:
                await message.reply_text(
                    strings.VERIFY_READ_RULES_CONTENT.format(
                        content=captcha_content[:4000]
                    )
                )
            else:
                await message.reply_text(strings.VERIFY_SEND_SECRET)
    elif args and args[0] == "CoCDoneLink":
        await _verify_user(user, captcha_service, context, message)
    else:
        await message.reply_text(strings.START_GREETING)


async def _verify_user(
    user,
    captcha_service: CaptchaService,
    context: ContextTypes.DEFAULT_TYPE,
    message,
) -> None:
    """Verify a user globally and unrestrict in all pending groups."""
    if await captcha_service.is_globally_verified(user.id):
        await message.reply_text(strings.VERIFY_ALREADY_VERIFIED)
        return

    pending_chats = await captcha_service.get_pending_chats(user.id)
    if not pending_chats:
        await message.reply_text(strings.VERIFY_NO_PENDING)
        return

    await captcha_service.verify_user_globally(user.id)

    for chat_id in pending_chats:
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user.id,
                permissions=captcha_service.get_full_permissions(),
            )
        except Exception as e:
            logger.warning(
                "Could not unrestrict user %s in chat %s: %s", user.id, chat_id, e
            )

    await message.reply_text(strings.VERIFY_SUCCESS)


async def _handle_private_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle private messages: check for secret command and verify user globally."""
    captcha_service: CaptchaService = context.bot_data["captcha_service"]
    message = update.message
    if message is None or message.text is None:
        return

    user = update.effective_user
    if user is None:
        return

    if not captcha_service.is_secret_command(message.text):
        await message.reply_text(strings.VERIFY_UNKNOWN_COMMAND)
        return

    await _verify_user(user, captcha_service, context, message)
