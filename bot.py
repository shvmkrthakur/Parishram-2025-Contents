#!/usr/bin/env python3
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ---------------- CONFIG ----------------
BOT_TOKEN = "8350446980:AAFvDRRnEQQ5kb_37Zss-LJAwBx6CdhLous"
BACKUP_CHANNEL_ID = -1002066954690   # replace with backup channel ID
MAIN_CHANNEL_ID = "@helloeveryone1227"    # replace with main channel ID

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ---------------- HANDLER ----------------
async def forward_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == BACKUP_CHANNEL_ID and update.message.video:
        try:
            # Download the video file
            video = await update.message.video.get_file()
            file_path = await video.download_to_drive()

            # Re-upload the video without thumbnail
            await context.bot.send_video(
                chat_id=MAIN_CHANNEL_ID,
                video=open(file_path, "rb"),
                caption=update.message.caption or "",
                thumbnail=None   # <-- force no thumbnail
            )

        except Exception as e:
            logging.error(f"Error: {e}")

# ---------------- MAIN ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.VIDEO, forward_video))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
