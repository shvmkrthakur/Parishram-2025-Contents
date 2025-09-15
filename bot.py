#!/usr/bin/env python3
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------------- CONFIG ----------------
BOT_TOKEN = "8350446980:AAFvDRRnEQQ5kb_37Zss-LJAwBx6CdhLous"
BACKUP_CHANNEL_ID = "@biologylectures1_0"   # replace with backup channel ID
MAIN_CHANNEL_ID = -1002999138018   # replace with main channel ID
      # main channel ID (numeric)

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ---------------- HANDLER ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /start <id> or /start <id1>-<id2>")
        return

    arg = context.args[0]

    try:
        # Single ID
        if "-" not in arg:
            msg_id = int(arg)
            await forward_video(update, context, msg_id)

        # Range of IDs
        else:
            start_id, end_id = map(int, arg.split("-"))
            if start_id > end_id:
                start_id, end_id = end_id, start_id

            for msg_id in range(start_id, end_id + 1):
                await forward_video(update, context, msg_id)

            await update.message.reply_text(f"✅ Forwarded videos {start_id} to {end_id}")

    except Exception as e:
        logging.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

# ---------------- FORWARD FUNCTION ----------------
async def forward_video(update: Update, context: ContextTypes.DEFAULT_TYPE, msg_id: int):
    try:
        # Fetch the original message
        msg = await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id=BACKUP_CHANNEL_ID,
            message_id=msg_id
        )

        if msg.video:
            # Re-send video using its file_id (no download, no custom thumbnail)
            await context.bot.send_video(
                chat_id=MAIN_CHANNEL_ID,
                video=msg.video.file_id,
                caption=msg.caption or "",
                thumbnail=None
            )
        else:
            await update.message.reply_text(f"Message {msg_id} is not a video ❌")

    except Exception as e:
        logging.error(f"Error forwarding {msg_id}: {e}")
        await update.message.reply_text(f"❌ Error forwarding {msg_id}: {e}")

# ---------------- MAIN ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
