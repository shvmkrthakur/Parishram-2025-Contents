#!/usr/bin/env python3
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------------- CONFIG ----------------
BOT_TOKEN = "8350446980:AAFvDRRnEQQ5kb_37Zss-LJAwBx6CdhLous"
BACKUP_CHANNEL_ID = "@biologylectures1_0"   # replace with backup channel ID
MAIN_CHANNEL_ID = -1002999138018   # replace with main channel ID
# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ---------------- START HANDLER ----------------
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
        # Step 1: Fetch the message directly (no download)
        msg = await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id=BACKUP_CHANNEL_ID,
            message_id=msg_id
        )

        if msg.video:
            file_id = msg.video.file_id

            # Step 2: Send video using file_id (auto thumbnail, no custom one)
            await context.bot.send_video(
                chat_id=MAIN_CHANNEL_ID,
                video=file_id,
                caption=msg.caption or ""
            )

            # Step 3: Delete the temp forward
            try:
                await msg.delete()
            except:
                pass

            await update.message.reply_text(f"✅ Forwarded video {msg_id} (up to 2 GB supported)")

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
