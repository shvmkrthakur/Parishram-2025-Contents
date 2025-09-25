#!/usr/bin/env python3
# merged_bot.py
# Combined script: keeps the new multi-step screenshot+UPI verification flow,
# and restores old user-facing texts, /verified, /redeem, ads flow, and legacy helpers.

import os
import json
import time
import hmac
import hashlib
import base64
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# ----------------- CONFIG -----------------
TOKEN = "8409312798:AAFNuh_AzYaXXoEdXyylITRw6ZXaoWg4V8E"  # <<<< keep your real token here (trimmed in this file for safety if needed)
# Replace the above token string with your actual token when deploying

SOURCE_CHANNEL = -1003008412138
JOIN_CHANNELS = ["@instahubackup", "@instahubackup2"]

# verification storage
VERIFY_FILE = "verified_users.json"
SECRET_KEY = b"G7r9Xm2qT5vB8zN4pL0sQwE6yH1uR3cKfVb9ZaP2"
REDEEM_WINDOW_SECONDS = 3 * 60 * 60
TOKEN_USAGE_FILE = "token_usage.json"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
SIG_LEN = 12

VERIFIED_CACHE = {}

# ----------------- MANUAL UPI/Screenshot VERIFICATION CONFIG -----------------
ADMIN_ID = 7347144999  # <-- REPLACE with your Telegram numeric ID if different
TEMP_VERIFY_SECONDS = 3600  # 1 hour temporary verification
TEMP_SUBMISSIONS = {}  # for multi-step screenshot -> upi flow

# ---------------- VERIFY HELPERS ----------------
def load_verified():
    global VERIFIED_CACHE
    if os.path.exists(VERIFY_FILE):
        try:
            with open(VERIFY_FILE, "r") as f:
                VERIFIED_CACHE = json.load(f)
        except Exception:
            VERIFIED_CACHE = {}
    else:
        VERIFIED_CACHE = {}

def save_verified():
    global VERIFIED_CACHE
    with open(VERIFY_FILE, "w") as f:
        json.dump(VERIFIED_CACHE, f)

def set_verified_for_seconds(user_id: int, seconds: int):
    global VERIFIED_CACHE
    now = time.time()
    current_expiry = VERIFIED_CACHE.get(str(user_id), 0)
    base = max(now, current_expiry)
    VERIFIED_CACHE[str(user_id)] = base + seconds
    save_verified()

def set_verified_24h(user_id: int):
    set_verified_for_seconds(user_id, 24 * 60 * 60)

def is_verified(user_id: int):
    global VERIFIED_CACHE
    key = str(user_id)
    if key in VERIFIED_CACHE:
        if time.time() < VERIFIED_CACHE[key]:
            return True
        # expired - cleanup
        del VERIFIED_CACHE[key]
        save_verified()
    return False

# ---------------- Token Usage (kept for backward compatibility storage, but token flow optional) ----------------
def load_token_usage():
    if os.path.exists(TOKEN_USAGE_FILE):
        try:
            with open(TOKEN_USAGE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_token_usage(data):
    with open(TOKEN_USAGE_FILE, "w") as f:
        json.dump(data, f)

# ---------------- Hatched Token System (helper functions left but token redemption flow optional) ----------------
def simple_decode(token: str) -> str:
    num = 0
    for ch in token:
        if ch not in ALPHABET:
            raise ValueError("Invalid character in token")
        num = num * len(ALPHABET) + ALPHABET.index(ch)
    if num == 0:
        return ""
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big")
    return raw.decode()

def validate_limit_token(token_str: str):
    try:
        raw = simple_decode(token_str)
    except Exception:
        return False, "❌ Invalid token or decode error.", 0, 0, ""

    parts = raw.split("|")
    if len(parts) != 4:
        return False, "❌ Invalid token format.", 0, 0, ""
    ddmmyy, limit_s, days_s, hours_s = parts
    try:
        limit = int(limit_s)
        days = int(days_s)
        hours = int(hours_s)
    except Exception:
        return False, "❌ Invalid numeric values in token.", 0, 0, ""

    today = time.strftime("%d%m%y")
    if ddmmyy != today:
        return False, "❌ Token expired or invalid date.", 0, 0, ""

    grant_seconds = days * 24 * 3600 + hours * 3600
    if grant_seconds <= 0:
        return False, "❌ Duration must be positive.", 0, 0, ""

    return True, "OK", grant_seconds, limit, raw

# ---------------- Legacy Code Validation ----------------
def validate_code_anyuser(code: str) -> bool:
    try:
        ts_str, sig = code.split("_", 1)
        ts = int(ts_str)
    except Exception:
        return False
    if abs(time.time() - ts) > 600:
        return False
    msg = ts_str.encode()
    expected = hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()[:SIG_LEN]
    return hmac.compare_digest(expected, sig)

# ---------------- Premium Token ----------------
def sign_payload_hex(payload: str) -> str:
    return hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()

def decode_premium_token(token_b64: str):
    try:
        raw = base64.b64decode(token_b64).decode()
    except Exception:
        return False, "Token is not valid base64.", None, None
    if "|" not in raw:
        return False, "Token payload malformed.", None, None
    parts = raw.rsplit("|", 1)
    if len(parts) != 2:
        return False, "Token malformed.", None, None
    payload, hex_sig = parts
    if not hex_sig or len(hex_sig) < 10:
        return False, "Invalid signature part.", None, None
    return True, "OK", payload, hex_sig

def validate_premium_token_for_user(token_b64: str, actual_user_id: int):
    ok, msg, payload, hex_sig = decode_premium_token(token_b64)
    if not ok:
        return False, msg, 0

    parts = payload.split("|")
    if len(parts) != 4:
        return False, "Invalid payload fields.", 0
    try:
        ts = int(parts[0])
        uid = int(parts[1])
        days = int(parts[2])
        hours = int(parts[3])
    except Exception:
        return False, "Payload contains invalid integers.", 0

    if uid != actual_user_id:
        return False, "Token is not for this user.", 0

    if time.time() - ts > REDEEM_WINDOW_SECONDS:
        return False, "Token redeem window (3h) has passed.", 0

    expected_hex = sign_payload_hex(payload)
    if not hmac.compare_digest(expected_hex, hex_sig):
        return False, "Signature mismatch.", 0

    grant_seconds = days * 24 * 3600 + hours * 3600
    if grant_seconds <= 0:
        return False, "Duration must be positive.", 0

    return True, "OK", grant_seconds


# ----------------- BOT BUTTON STORAGE -----------------
BOTS_FILE = "bots.json"
BOTS = {}

def load_bots():
    global BOTS
    if os.path.exists(BOTS_FILE):
        try:
            with open(BOTS_FILE, "r") as f:
                BOTS = json.load(f)
        except:
            BOTS = {}
    else:
        BOTS = {}

def save_bots():
    global BOTS
    with open(BOTS_FILE, "w") as f:
        json.dump(BOTS, f)

# ---------------- BOT COMMANDS ----------------
async def addbot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /addbot BotName BotURL")
        return
    name, url = context.args[0], context.args[1]
    BOTS[name] = url
    save_bots()
    await update.message.reply_text(f"✅ Added bot: {name} → {url}")

async def addurl_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /addurl BotName NewURL")
        return
    name, url = context.args[0], context.args[1]
    if name not in BOTS:
        await update.message.reply_text("❌ Bot not found. Use /addbot first.")
        return
    BOTS[name] = url
    save_bots()
    await update.message.reply_text(f"🔄 Updated {name} URL → {url}")


# ----------------- BOT1/BOT2 URL STORAGE -----------------
BOTURLS_FILE = "bot_urls.json"
BOT_URLS = {"BOT1": "https://t.me/YourBot1", "BOT2": "https://t.me/YourBot2"}

def load_bot_urls():
    global BOT_URLS
    if os.path.exists(BOTURLS_FILE):
        try:
            with open(BOTURLS_FILE, "r") as f:
                BOT_URLS = json.load(f)
        except:
            pass

def save_bot_urls():
    global BOT_URLS
    with open(BOTURLS_FILE, "w") as f:
        json.dump(BOT_URLS, f)

# ---------------- BOT URL COMMANDS ----------------
async def addurl1_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Usage: /addurl1 NewURL")
        return
    url = context.args[0]
    BOT_URLS["BOT1"] = url
    save_bot_urls()
    await update.message.reply_text(f"🔄 Updated BOT1 URL → {url}")
    # Show updated menu
    await update.message.reply_text("📌 Updated Verify Menu:", reply_markup=verify_menu_kb())

async def addurl2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not authorized.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Usage: /addurl2 NewURL")
        return
    url = context.args[0]
    BOT_URLS["BOT2"] = url
    save_bot_urls()
    await update.message.reply_text(f"🔄 Updated BOT2 URL → {url}")
    # Show updated menu
    await update.message.reply_text("📌 Updated Verify Menu:", reply_markup=verify_menu_kb())

# ---------------- HELPERS ----------------
async def check_user_in_channels(bot, user_id):
    for channel in JOIN_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

# ---------------- UPDATED VERIFY MENU ----------------
def verify_menu_kb():
    # Always load latest BOT1 and BOT2 URLs from bot_urls.json
    load_bot_urls()
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 BOT 1", url=BOT_URLS.get("BOT1", "https://t.me/YourBot1")),
            InlineKeyboardButton("🤖 BOT 2", url=BOT_URLS.get("BOT2", "https://t.me/YourBot2"))
        ],
        [InlineKeyboardButton("📤 Send 2 Screenshots + UPI", callback_data="send_ss_upi")],
        [InlineKeyboardButton("🚫 Remove Ads / Any Doubt", callback_data="remove_ads")]
    ])
     

# ---------------- HANDLERS ----------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "User"

    if text == "/start":
        if not await check_user_in_channels(context.bot, user_id):
            keyboard = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{ch.replace('@','')}")] for ch in JOIN_CHANNELS]
            keyboard.append([InlineKeyboardButton("🔄 I Joined, Retry", callback_data="check_join")])
            await update.message.reply_text(
                f"👋 Hi {username}!\n\n"
                "To continue using this bot, please join all the required backup channels first.\n\n"
                "👉 Once done, tap **Retry** below.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return

        if is_verified(user_id):
            await update.message.reply_text(
                "✅ You’re already verified!\n\nGo to [Insta Hub](https://t.me/+te3K1qRT9i41ZWU1), choose a video, and I’ll send it here for you.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"👋 Welcome {username}!\n\n"
                "This bot helps you get videos from [Insta Hub](https://t.me/+te3K1qRT9i41ZWU1).\n\n"
                "🔒 Please verify yourself to unlock access. If you done the bots earilier then contact bot admin @Piyush76785",
                reply_markup=verify_menu_kb(),
                parse_mode="Markdown"
            )
        return

    # If message contains numeric payloads (video IDs), keep existing behavior
    if " " in text:
        payload = text.split(" ", 1)[1].strip()
    else:
        payload = text[len("/start"):].strip()

    # NOTE: Old token-based branches removed. Verification is now via screenshot+UPI only.
    if payload.isdigit() or "-" in payload or "&" in payload:
        video_ids = []

        if "-" in payload:
            try:
                start_id, end_id = map(int, payload.split("-"))
                if start_id <= end_id:
                    video_ids = list(range(start_id, end_id + 1))
            except Exception:
                await update.message.reply_text("❌ Invalid range format. Use like 1-4.")
                return

        elif "&" in payload:
            try:
                video_ids = [int(x) for x in payload.split("&") if x.isdigit()]
            except Exception:
                await update.message.reply_text("❌ Invalid multi-ID format. Use like 1&2&5.")
                return

        else:
            try:
                video_ids = [int(payload)]
            except:
                video_ids = []

        if not await check_user_in_channels(context.bot, user_id):
            keyboard = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{ch.replace('@','')}")] for ch in JOIN_CHANNELS]
            keyboard.append([InlineKeyboardButton("🔄 I Joined, Retry", callback_data="check_join")])
            await update.message.reply_text("🔒 Please join all required backup channels to continue.", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if is_verified(user_id):
            sent = 0
            for vid in video_ids:
                try:
                    await context.bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=SOURCE_CHANNEL,
                        message_id=vid,
                        protect_content=True
                    )
                    sent += 1
                except Exception as e:
                    await update.message.reply_text(f"⚠️ Couldn’t send video ID {vid}. Error: {e}")
            if sent > 0:
                await update.message.reply_text(f"✅ Sent {sent} video(s).")
        else:
            await update.message.reply_text(
                "🔒 You haven’t verified yet.\n\nPlease complete verification first to unlock video access.If you done the bots earilier then contact bot admin @Piyush76785",
                reply_markup=verify_menu_kb()
            )
        return

# Handler for the "I Joined, Retry" callback
async def join_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.first_name or "User"
    await query.answer()

    if not await check_user_in_channels(context.bot, user_id):
        keyboard = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{ch.replace('@','')}")] for ch in JOIN_CHANNELS]
        keyboard.append([InlineKeyboardButton("🔄 I Joined, Retry", callback_data="check_join")])
        await query.edit_message_text(
            f"👋 Hi {username},\n\n"
            "You still haven’t joined all the required backup channels.\n\n"
            "👉 Please join them and then hit Retry.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        if is_verified(user_id):
            await query.edit_message_text(
                "✅ You’re already verified!\n\nGo back to [Insta Hub](https://t.me/+te3K1qRT9i41ZWU1), choose a video, and I’ll deliver it here.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"👋 Welcome {username}!\n\n"
                "Before accessing videos, please verify yourself by sending two screenshots + UPI. If you done the bots earilier then contact bot admin @Piyush76785",
                reply_markup=verify_menu_kb(),
                parse_mode="Markdown"
            )

# ---------------- ADS / REMOVE ADS ----------------
async def remove_ads_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    username = update.effective_user.first_name or "User"
    await query.answer()

    text = (
        f"👋 Hey {username},\n\n"
        "✨ Upgrade to **Premium Membership** and enjoy ad-free, unlimited access:\n\n"
        "📌 Plans:\n"
        "• 7 Days – ₹30\n"
        "• 1 Month – ₹110\n"
        "• 3 Months – ₹299\n"
        "• 6 Months – ₹550\n"
        "• 1 Year – ₹999\n\n"
        "💵 Pay via UPI ID: `roshanbot@fam`\n\n"
        "📸 [Scan QR Code](https://insta-hub.netlify.app/qr.png)\n\n"
        "⚠️ If payment fails on QR, contact the admin.\n\n"
        "📤 Don’t forget to send a payment screenshot after completing the transaction!"
    )

    keyboard = [
        [InlineKeyboardButton("📤 Send Screenshot(Admin)", url="https://t.me/Instahubpaymentcheckbot")],
        [InlineKeyboardButton("❌ Close", callback_data="close_ads")]
    ]

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def close_ads_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    username = update.effective_user.first_name or "User"
    await query.answer()

    if is_verified(user_id):
        await query.edit_message_text(
            "✅ You’re verified!\n\nGo back to [Insta Hub](https://t.me/+te3K1qRT9i41ZWU1), select a video, and I’ll send it here.",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"👋 Hi {username}!\n\nPlease complete verification first to unlock 24-hour video access. Contact Admin @Piyush76785 If you done this bot .",
            reply_markup=verify_menu_kb()
        )

# ---------------- VERIFIED HANDLER (legacy verification code kept) ----------------
async def verified_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id

    code = None
    if text.startswith("/verified="):
        code = text.replace("/verified=", "", 1).strip()
    elif text.startswith("/verified "):
        code = text.split(" ", 1)[1].strip()

    if not code:
        await update.message.reply_text("⚠️ Invalid format.\n\nUse: `/verified=YOUR_CODE`")
        return

    # keep legacy validation for other systems, but prefer screenshot/UPI flow
    if validate_code_anyuser(code):
        set_verified_24h(user_id)
        await update.message.reply_text(
            "🎉 Success! You’re verified for the next 24 hours.\n\nGo back to  [Insta Hub](https://t.me/+te3K1qRT9i41ZWU1) and request your videos.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Invalid or expired verification code.")

# ---------------- REDEEM HANDLER (kept intact for premium tokens) ----------------
async def redeem_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        await update.message.reply_text("⚠️ Usage:\n`/redeem <TOKEN>`")
        return
    token = parts[1].strip()

    ok, msg, grant_seconds = validate_premium_token_for_user(token, user_id)
    if ok:
        set_verified_for_seconds(user_id, grant_seconds)
        days = grant_seconds // (24*3600)
        hours = (grant_seconds % (24*3600)) // 3600
        await update.message.reply_text(f"🎉 Premium redeemed!\n\n✅ You’re verified for {days} day(s) and {hours} hour(s). Enjoy your access!")
    else:
        await update.message.reply_text(f"❌ {msg}")

# ---------------- NEW: Multi-step Screenshot + UPI handlers ----------------
async def send_ss_upi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📤 Please send *first* screenshot now. \n\n Warning :- Send proper screenshot of bot task if you send wrong screen shot you will be kicked from instahub group", parse_mode='Markdown')

async def ss_upi_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.first_name or "User"
    # Accept only photos for the multi-step flow
    if not update.message.photo:
        await update.message.reply_text("⚠️ Please send a screenshot photo.")
        return
    file_id = update.message.photo[-1].file_id
    sub = TEMP_SUBMISSIONS.get(str(user_id))
    if not sub:
        # first screenshot
        TEMP_SUBMISSIONS[str(user_id)] = {"photos": [file_id], "state": "awaiting_second", "upi": None, "username": username}
        await update.message.reply_text("✅ First screenshot received. Now send *second* screenshot.", parse_mode='Markdown')
        return
    if sub["state"] == "awaiting_second":
        sub["photos"].append(file_id)
        sub["state"] = "awaiting_upi"
        TEMP_SUBMISSIONS[str(user_id)] = sub
        await update.message.reply_text("✅ Second screenshot received. Now send your *UPI ID* as plain text. If you don't have any upi id enter your telegram username or phone number admin will contact you.", parse_mode='Markdown')
        return
    if sub["state"] == "awaiting_upi":
        await update.message.reply_text("⚠️ Already got 2 screenshots, now send UPI text.")
        return

async def upi_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    text = (update.message.text or "").strip()
    sub = TEMP_SUBMISSIONS.get(str(user_id))
    if not sub or sub["state"] != "awaiting_upi":
        return
    sub["upi"] = text
    sub["submitted_time"] = int(time.time())
    sub["state"] = "submitted"
    TEMP_SUBMISSIONS[str(user_id)] = sub
    set_verified_for_seconds(user_id, TEMP_VERIFY_SECONDS)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
                                      InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]])
    caption = (
        f"🆕 Verification Request\n"
        f"User: {sub['username']} (ID: {user_id})\n"
        f"UPI: {sub['upi']}\n"
        f"Submitted: {datetime.fromtimestamp(sub['submitted_time']).strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
        # send first photo with caption+buttons, and second photo separately
        msg = await context.bot.send_photo(chat_id=ADMIN_ID, photo=sub["photos"][0], caption=caption, reply_markup=keyboard)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=sub["photos"][1], caption=f"Second screenshot for user {user_id}")
        sub["admin_msg_id"] = msg.message_id
        TEMP_SUBMISSIONS[str(user_id)] = sub
    except Exception as e:
        await update.message.reply_text(f"⚠️ Could not forward to admin. Error: {e}")
        # rollback temp verify
        if str(user_id) in VERIFIED_CACHE:
            del VERIFIED_CACHE[str(user_id)]
            save_verified()
        return
    await update.message.reply_text("✅ Submitted to admin. You are temporarily verified for 1 hour.")

async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    try:
        target_user = int(data.split("_", 1)[1])
    except Exception:
        await query.edit_message_text("❌ Invalid callback data.")
        return
    if data.startswith("approve_"):
        set_verified_24h(target_user)
        try:
            await context.bot.send_message(target_user, "🎉 Approved! ✅ You now have 24h access.")
        except:
            pass
        await query.edit_message_caption(caption="✅ Approved by admin. Rs 1 is sent to your upi.")
    elif data.startswith("reject_"):
        # remove temporary verification
        if str(target_user) in VERIFIED_CACHE:
            del VERIFIED_CACHE[str(target_user)]
            save_verified()
        try:
            await context.bot.send_message(target_user, "❌ Rejected. Please try again.")
        except:
            pass
        await query.edit_message_caption(caption="❌ Rejected by admin.")

# ---------------- MAIN ----------------
def main():
    load_verified()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("verified", verified_handler))
    app.add_handler(CommandHandler("redeem", redeem_handler))
    app.add_handler(CallbackQueryHandler(join_check_callback, pattern="check_join"))
    app.add_handler(CallbackQueryHandler(remove_ads_callback, pattern="remove_ads"))
    app.add_handler(CallbackQueryHandler(close_ads_callback, pattern="close_ads"))

    # New handlers for screenshot verification flow (multi-step)
    app.add_handler(CallbackQueryHandler(send_ss_upi_callback, pattern="send_ss_upi"))
    app.add_handler(MessageHandler(filters.PHOTO, ss_upi_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, upi_text_handler))
    app.add_handler(CallbackQueryHandler(approval_callback, pattern="^(approve_|reject_)"))

    app.add_handler(CommandHandler("addbot", addbot_handler))
    app.add_handler(CommandHandler("addurl", addurl_handler))
    app.add_handler(CommandHandler("addurl1", addurl1_handler))
    app.add_handler(CommandHandler("addurl2", addurl2_handler))
    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
