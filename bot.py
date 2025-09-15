#!/usr/bin/env python3
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------------- CONFIG ----------------
BOT_TOKEN = "8350446980:AAFvDRRnEQQ5kb_37Zss-LJAwBx6CdhLous"
BACKUP_CHANNEL_ID = -1002066954690   # replace with backup channel ID
MAIN_CHANNEL_ID = -1002999138018   # replace with main channel ID

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ---------------- HELPERS ----------------
async def reupload_video(context: ContextTypes.DEFAULT_TYPE, message):
    """Download and re-upload a video without thumbnail."""
    if message.video:
        try:
            video = await message.video.get_file()
            file_path = await video.download_to_drive()

            with open(file_path, "rb") as f:
                await context.bot.send_video(
                    chat_id=MAIN_CHANNEL_ID,
                    video=f,
                    caption=message.caption or "",
                    thumbnail=None
                )
        except Exception as e:
            logging.error(f"Error reuploading video: {e}")

# ---------------- COMMAND HANDLER ----------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start commands with video IDs like /start 1-4 or /start 5"""
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /start 1-4 or /start 5")
        return

    try:
        if "-" in args[0]:
            start_id, end_id = map(int, args[0].split("-"))
            ids = range(start_id, end_id + 1)
        else:
            ids = [int(args[0])]

        for mid in ids:
            try:
                # Fetch the original message from backup channel
                msg = await context.bot.forward_message(
                    chat_id=update.effective_chat.id,  # temporary forward
                    from_chat_id=BACKUP_CHANNEL_ID,
                    message_id=mid
                )
                # Reupload to main channel without thumbnail
                await reupload_video(context, msg)
                await msg.delete()  # remove temp forward
            except Exception as e:
                logging.error(f"Error fetching message {mid}: {e}")

        await update.message.reply_text(f"Forwarded videos: {args[0]} ✅")

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ---------------- MAIN ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
