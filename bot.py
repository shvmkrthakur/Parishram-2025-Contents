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

# ---------------- HANDLER ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /start <message_id>")
        return

    try:
        msg_id = int(context.args[0])  # message ID from command
        # fetch the message from backup channel
        msg = await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id=BACKUP_CHANNEL_ID,
            message_id=msg_id
        )

        if msg.video:
            file = await msg.video.get_file()
            file_path = await file.download_to_drive()

            await context.bot.send_video(
                chat_id=MAIN_CHANNEL_ID,
                video=open(file_path, "rb"),
                caption=msg.caption or "",
                thumbnail=None
            )
            await update.message.reply_text(f"Forwarded video {msg_id} ✅")
        else:
            await update.message.reply_text("That message is not a video ❌")

    except Exception as e:
        logging.error(f"Error: {e}")
        await update.message.reply_text(f"Error: {e}")

# ---------------- MAIN ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
