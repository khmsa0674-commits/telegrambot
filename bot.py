"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ██╗   ██╗██╗██████╗ ███████╗ ██████╗     ██████╗  ██████╗ ████████╗  ║
║   ██║   ██║██║██╔══██╗██╔════╝██╔═══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝  ║
║   ██║   ██║██║██║  ██║█████╗  ██║   ██║    ██████╔╝██║   ██║   ██║     ║
║   ╚██╗ ██╔╝██║██║  ██║██╔══╝  ██║   ██║    ██╔══██╗██║   ██║   ██║     ║
║    ╚████╔╝ ██║██████╔╝███████╗╚██████╔╝    ██████╔╝╚██████╔╝   ██║     ║
║     ╚═══╝  ╚═╝╚═════╝ ╚══════╝ ╚═════╝     ╚═════╝  ╚═════╝    ╚═╝     ║
║                                                                  ║
║   🎬 TikTok • Instagram • YouTube Downloader Bot                ║
║   ⚙️  Admin Panel • Broadcast • Force Subscribe                  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import logging
import os

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError, Forbidden

import config
import database as db
from downloader import (
    download_video,
    is_supported_url,
    detect_platform,
    cleanup_file,
    ensure_download_dir,
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s │ %(levelname)s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────
BROADCAST_TEXT = 1
ADD_CHANNEL     = 2
BAN_USER_ID     = 3

# ── Platform emojis ───────────────────────────────────────────────────────────
PLATFORM_EMOJI = {
    "tiktok":    "🎵",
    "instagram": "📸",
    "youtube":   "▶️",
}

PLATFORM_NAME = {
    "tiktok":    "TikTok",
    "instagram": "Instagram",
    "youtube":   "YouTube",
}


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def check_subscription(bot, user_id: int) -> list[dict]:
    """Returns list of channels the user is NOT subscribed to"""
    if not config.CHECK_SUBSCRIPTION:
        return []

    channels = db.get_active_channels()
    if not channels:
        return []

    not_subscribed = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel["channel_id"], user_id)
            if member.status in ("left", "kicked", "banned"):
                not_subscribed.append(channel)
        except TelegramError:
            not_subscribed.append(channel)

    return not_subscribed


async def get_channel_links(bot, channels: list[dict]) -> str:
    """Build subscription channel links text"""
    lines = []
    for i, ch in enumerate(channels, 1):
        cid = ch["channel_id"]
        title = ch.get("title") or cid
        try:
            chat = await bot.get_chat(cid)
            link = f"https://t.me/{chat.username}" if chat.username else cid
            lines.append(f"{i}. <a href='{link}'>{title}</a>")
        except Exception:
            lines.append(f"{i}. {title}")
    return "\n".join(lines)


def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_sub")
    ]])


# ══════════════════════════════════════════════════════════════════
#  USER COMMANDS
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)

    if db.is_banned(user.id):
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت")
        return

    await update.message.reply_html(
        config.MESSAGES["welcome"],
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📌 المساعدة", callback_data="show_help")],
        ])
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)
    await update.message.reply_html(config.MESSAGES["help"])


# ══════════════════════════════════════════════════════════════════
#  VIDEO DOWNLOAD HANDLER
# ══════════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()

    # Register / update user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)

    # ── Ban check ──────────────────────────────────────────────────
    if db.is_banned(user.id):
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت")
        return

    # ── Subscription check ────────────────────────────────────────
    missing = await check_subscription(context.bot, user.id)
    if missing:
        channels_text = await get_channel_links(context.bot, missing)
        await update.message.reply_html(
            config.MESSAGES["not_subscribed"].format(channels=channels_text),
            reply_markup=subscription_keyboard(),
        )
        return

    # ── URL detection ─────────────────────────────────────────────
    if not is_supported_url(text):
        await update.message.reply_html(config.MESSAGES["error_invalid_link"])
        return

    platform = detect_platform(text)
    emoji    = PLATFORM_EMOJI.get(platform, "🎬")
    pname    = PLATFORM_NAME.get(platform, platform)

    # ── Daily limit check ─────────────────────────────────────────
    if (config.MAX_DOWNLOADS_PER_USER > 0
            and not db.is_premium(user.id)
            and not is_admin(user.id)):
        today_count = db.get_today_downloads(user.id)
        if today_count >= config.MAX_DOWNLOADS_PER_USER:
            await update.message.reply_html(
                config.MESSAGES["daily_limit"].format(
                    max=config.MAX_DOWNLOADS_PER_USER
                )
            )
            return

    # ── Download ──────────────────────────────────────────────────
    status_msg = await update.message.reply_html(
        f"{emoji} {config.MESSAGES['downloading']}"
    )

    result = await download_video(text)

    if not result.success:
        error_map = {
            "private":    config.MESSAGES["error_private"],
            "too_large":  config.MESSAGES["error_too_large"].format(
                            size=config.MAX_FILE_SIZE_MB),
            "unsupported": config.MESSAGES["error_invalid_link"],
            "not_found":  config.MESSAGES["error_invalid_link"],
            "geo_blocked": "⚠️ هذا المحتوى غير متاح في منطقتك",
            "removed":    "⚠️ تم حذف هذا المحتوى من المنصة",
            "general":    config.MESSAGES["error_general"],
        }
        error_text = error_map.get(result.error, config.MESSAGES["error_general"])
        await status_msg.edit_text(error_text)
        db.log_download(user.id, platform or "unknown", text, "failed")
        return

    # ── Send video ────────────────────────────────────────────────
    try:
        await status_msg.edit_text(config.MESSAGES["sending"])

        caption = (
            f"{emoji} <b>{result.title}</b>\n"
            f"📌 المصدر: {pname}\n"
            f"🤖 @{(await context.bot.get_me()).username}"
        )
        if result.duration:
            m, s = divmod(result.duration, 60)
            caption += f"\n⏱ المدة: {m:02d}:{s:02d}"

        with open(result.file_path, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=caption,
                parse_mode="HTML",
                supports_streaming=True,
                read_timeout=60,
                write_timeout=120,
                connect_timeout=30,
            )

        await status_msg.delete()
        db.log_download(user.id, platform, text, "success")
        logger.info("✅ [%s] Downloaded %s for user %d", pname, result.title[:40], user.id)

    except TelegramError as e:
        logger.error("Send error: %s", e)
        await status_msg.edit_text(config.MESSAGES["error_general"])
        db.log_download(user.id, platform, text, "failed")

    finally:
        if result.file_path:
            cleanup_file(result.file_path)


# ══════════════════════════════════════════════════════════════════
#  CALLBACK QUERIES
# ══════════════════════════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user  = update.effective_user
    data  = query.data

    if data == "show_help":
        await query.message.reply_html(config.MESSAGES["help"])

    elif data == "check_sub":
        missing = await check_subscription(context.bot, user.id)
        if missing:
            channels_text = await get_channel_links(context.bot, missing)
            await query.message.edit_reply_markup(subscription_keyboard())
            await query.answer("❌ لم تشترك بعد في جميع القنوات!", show_alert=True)
        else:
            await query.message.edit_text("✅ تم التحقق! يمكنك الآن استخدام البوت 🎉")

    # ── Admin callbacks ───────────────────────────────────────────
    elif data == "admin_panel":
        if not is_admin(user.id):
            return
        await show_admin_panel(query.message, edit=True)

    elif data == "admin_stats":
        if not is_admin(user.id):
            return
        await show_stats(query.message, edit=True)

    elif data == "admin_channels":
        if not is_admin(user.id):
            return
        await show_channels_panel(query.message, context, edit=True)

    elif data.startswith("del_channel:"):
        if not is_admin(user.id):
            return
        ch_id = data.split(":", 1)[1]
        db.remove_channel(ch_id)
        await query.answer("✅ تم حذف القناة")
        await show_channels_panel(query.message, context, edit=True)

    elif data.startswith("toggle_sub:"):
        if not is_admin(user.id):
            return
        new_val = data.split(":")[1] == "1"
        config.CHECK_SUBSCRIPTION = new_val
        await query.answer(f"{'✅ تم تفعيل' if new_val else '❌ تم إيقاف'} الاشتراك الإجباري")
        await show_channels_panel(query.message, context, edit=True)


# ══════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ هذا الأمر للأدمنات فقط")
        return
    await show_admin_panel(update.message)


async def show_admin_panel(message, edit: bool = False):
    stats = db.get_users_count()
    dl    = db.get_download_stats()

    text = (
        "🛠 <b>لوحة تحكم الأدمن</b>\n\n"
        f"👥 المستخدمون: <b>{stats['total']}</b> (اليوم: +{stats['today']})\n"
        f"🌟 المميزون: <b>{stats['premium']}</b>\n"
        f"📥 التنزيلات الكلية: <b>{dl['total']}</b> (اليوم: {dl['today']})\n\n"
        "اختر ما تريد:"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 إرسال رسالة جماعية", callback_data="start_broadcast"),
            InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton("📡 إدارة القنوات", callback_data="admin_channels"),
        ],
    ])

    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.reply_html(text, reply_markup=keyboard)


async def show_stats(message, edit: bool = False):
    stats = db.get_users_count()
    dl    = db.get_download_stats()
    by_p  = dl.get("by_platform", {})

    platform_lines = "\n".join(
        f"   {PLATFORM_EMOJI.get(p,'▸')} {PLATFORM_NAME.get(p,p)}: <b>{c}</b>"
        for p, c in by_p.items()
    ) or "   لا يوجد بيانات بعد"

    text = (
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"👥 إجمالي المستخدمين: <b>{stats['total']}</b>\n"
        f"✅ مستخدمون نشطون: <b>{stats['active']}</b>\n"
        f"🌟 مستخدمون مميزون: <b>{stats['premium']}</b>\n"
        f"🆕 اليوم: <b>+{stats['today']}</b>\n\n"
        f"📥 إجمالي التنزيلات: <b>{dl['total']}</b>\n"
        f"📅 تنزيلات اليوم: <b>{dl['today']}</b>\n\n"
        f"<b>حسب المنصة:</b>\n{platform_lines}"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")
    ]])

    if edit:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.reply_html(text, reply_markup=keyboard)


async def show_channels_panel(message, context, edit: bool = False):
    channels = db.get_active_channels()
    sub_status = "✅ مفعّل" if config.CHECK_SUBSCRIPTION else "❌ موقف"

    text = (
        f"📡 <b>إدارة قنوات الاشتراك الإجباري</b>\n\n"
        f"الحالة: {sub_status}\n\n"
    )

    buttons = []
    if channels:
        text += "<b>القنوات المضافة:</b>\n"
        for ch in channels:
            cid   = ch["channel_id"]
            title = ch.get("title") or cid
            text += f"• {title} ({cid})\n"
            buttons.append([InlineKeyboardButton(
                f"🗑 حذف {title}", callback_data=f"del_channel:{cid}"
            )])
    else:
        text += "لا توجد قنوات مضافة حالياً\n"

    toggle_val  = "0" if config.CHECK_SUBSCRIPTION else "1"
    toggle_text = "❌ إيقاف الاشتراك الإجباري" if config.CHECK_SUBSCRIPTION else "✅ تفعيل الاشتراك الإجباري"

    buttons += [
        [InlineKeyboardButton(toggle_text, callback_data=f"toggle_sub:{toggle_val}")],
        [InlineKeyboardButton("➕ إضافة قناة (أرسل /addchannel)", callback_data="admin_panel")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
    ]

    if edit:
        await message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
        )
    else:
        await message.reply_html(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )


# ── /broadcast ───────────────────────────────────────────────────────────────

async def cmd_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_html(
        "📢 <b>إرسال رسالة جماعية</b>\n\n"
        "أرسل الرسالة التي تريد إيصالها لجميع المستخدمين\n"
        "(يدعم النص العادي والـ HTML)\n\n"
        "/cancel للإلغاء"
    )
    return BROADCAST_TEXT


async def cmd_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    broadcast_message = update.message

    users     = db.get_all_users()
    total     = len(users)
    sent      = 0
    failed    = 0

    progress  = await update.message.reply_html(
        f"📤 جارٍ الإرسال...\n0 / {total}"
    )

    for i, uid in enumerate(users, 1):
        try:
            await broadcast_message.copy(uid)
            sent += 1
        except Forbidden:
            db.ban_user(uid)   # user blocked the bot
            failed += 1
        except TelegramError:
            failed += 1

        # Update progress every 30 users
        if i % 30 == 0 or i == total:
            try:
                await progress.edit_text(
                    f"📤 جارٍ الإرسال... {i}/{total}\n"
                    f"✅ نجح: {sent}  ❌ فشل: {failed}"
                )
            except TelegramError:
                pass
            await asyncio.sleep(0.5)   # Flood control

    db.log_broadcast(
        update.effective_user.id,
        str(broadcast_message.text or "[media]"),
        sent,
        failed,
    )

    await progress.edit_text(
        config.MESSAGES["broadcast_confirm"].format(count=sent) +
        f"\n❌ فشل: {failed}"
    )
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء")
    return ConversationHandler.END


# ── /addchannel ──────────────────────────────────────────────────────────────

async def cmd_addchannel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_html(
        "📡 <b>إضافة قناة اشتراك إجباري</b>\n\n"
        "أرسل معرف القناة أو رابطها:\n"
        "• مثال: <code>@mychannel</code>\n"
        "• أو: <code>-1001234567890</code>\n\n"
        "⚠️ تأكد من إضافة البوت كأدمن في القناة\n\n"
        "/cancel للإلغاء"
    )
    return ADD_CHANNEL


async def cmd_addchannel_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    channel_input = update.message.text.strip()

    # Normalize input
    if channel_input.startswith("https://t.me/"):
        channel_input = "@" + channel_input.replace("https://t.me/", "")

    try:
        chat  = await context.bot.get_chat(channel_input)
        title = chat.title or channel_input
        cid   = str(chat.id) if not channel_input.startswith("@") else channel_input
        db.add_channel(cid, title)
        await update.message.reply_html(
            f"✅ تمت إضافة القناة: <b>{title}</b>\n"
            f"المعرف: <code>{cid}</code>"
        )
    except TelegramError as e:
        await update.message.reply_html(
            f"❌ تعذر إضافة القناة\n"
            f"تأكد أن البوت أدمن فيها وأن المعرف صحيح\n\n"
            f"<code>{e}</code>"
        )

    return ConversationHandler.END


# ── /ban & /unban ────────────────────────────────────────────────────────────

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("الاستخدام: /ban [user_id]")
        return
    try:
        uid = int(context.args[0])
        db.ban_user(uid, True)
        await update.message.reply_html(f"🚫 تم حظر المستخدم <code>{uid}</code>")
    except ValueError:
        await update.message.reply_text("❌ معرف غير صحيح")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("الاستخدام: /unban [user_id]")
        return
    try:
        uid = int(context.args[0])
        db.ban_user(uid, False)
        await update.message.reply_html(f"✅ تم رفع الحظر عن <code>{uid}</code>")
    except ValueError:
        await update.message.reply_text("❌ معرف غير صحيح")


async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("الاستخدام: /premium [user_id]")
        return
    try:
        uid = int(context.args[0])
        db.set_premium(uid, True)
        await update.message.reply_html(f"🌟 تم تعيين <code>{uid}</code> كمستخدم مميز")
    except ValueError:
        await update.message.reply_text("❌ معرف غير صحيح")


async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("الاستخدام: /userinfo [user_id]")
        return
    try:
        uid  = int(context.args[0])
        user = db.get_user(uid)
        if not user:
            await update.message.reply_text("❌ المستخدم غير موجود في قاعدة البيانات")
            return
        dls_today = db.get_today_downloads(uid)
        await update.message.reply_html(
            f"👤 <b>معلومات المستخدم</b>\n\n"
            f"🆔 المعرف: <code>{uid}</code>\n"
            f"👤 الاسم: {user['first_name'] or ''} {user['last_name'] or ''}\n"
            f"📛 اليوزرنيم: @{user['username'] or 'لا يوجد'}\n"
            f"🌟 مميز: {'نعم ✅' if user['is_premium'] else 'لا'}\n"
            f"🚫 محظور: {'نعم ⛔' if user['is_banned'] else 'لا'}\n"
            f"📅 انضم: {user['joined_at'][:10]}\n"
            f"⏱ آخر نشاط: {user['last_seen'][:16]}\n"
            f"📥 تنزيلات اليوم: {dls_today}"
        )
    except ValueError:
        await update.message.reply_text("❌ معرف غير صحيح")


# ══════════════════════════════════════════════════════════════════
#  BOT STARTUP
# ══════════════════════════════════════════════════════════════════

async def set_commands(app):
    user_cmds  = [
        BotCommand("start", "بدء البوت"),
        BotCommand("help",  "المساعدة والتعليمات"),
    ]
    admin_cmds = user_cmds + [
        BotCommand("admin",      "لوحة تحكم الأدمن"),
        BotCommand("broadcast",  "إرسال رسالة لجميع المستخدمين"),
        BotCommand("addchannel", "إضافة قناة اشتراك إجباري"),
        BotCommand("ban",        "حظر مستخدم"),
        BotCommand("unban",      "رفع الحظر عن مستخدم"),
        BotCommand("premium",    "منح صلاحيات مميزة"),
        BotCommand("userinfo",   "معلومات مستخدم"),
    ]

    await app.bot.set_my_commands(user_cmds)
    for admin_id in config.ADMIN_IDS:
        try:
            await app.bot.set_my_commands(
                admin_cmds,
                scope={"type": "chat", "chat_id": admin_id}
            )
        except TelegramError:
            pass


def build_application():
    db.init_db()
    ensure_download_dir()

    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # ── Broadcast conversation ─────────────────────────────────────
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", cmd_broadcast_start)],
        states={
            BROADCAST_TEXT: [
                MessageHandler(filters.ALL & ~filters.COMMAND, cmd_broadcast_send)
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    # ── Add channel conversation ───────────────────────────────────
    addchannel_conv = ConversationHandler(
        entry_points=[CommandHandler("addchannel", cmd_addchannel_start)],
        states={
            ADD_CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_addchannel_save)
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    # ── Register handlers ──────────────────────────────────────────
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("admin",    cmd_admin))
    app.add_handler(CommandHandler("ban",      cmd_ban))
    app.add_handler(CommandHandler("unban",    cmd_unban))
    app.add_handler(CommandHandler("premium",  cmd_premium))
    app.add_handler(CommandHandler("userinfo", cmd_userinfo))
    app.add_handler(broadcast_conv)
    app.add_handler(addchannel_conv)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # URL / video link handler
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

    app.post_init = set_commands
    return app


def main():
    print("""
╔══════════════════════════════════════════════╗
║       🎬  VideoBot is starting up!          ║
║                                              ║
║  TikTok • Instagram • YouTube Downloader     ║
╚══════════════════════════════════════════════╝
    """)

    if config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ خطأ: ضع توكن البوت في config.py")
        return

    app = build_application()
    logger.info("🚀 Bot started! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
