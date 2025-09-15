#!/usr/bin/env python3
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------------- CONFIG ----------------
BOT_TOKEN = "8350446980:AAFvDRRnEQQ5kb_37Zss-LJAwBx6CdhLous"
BACKUP_CHANNEL_ID = "@biologylectures1_0"   # replace with backup channel ID
MAIN_CHANNEL_ID = -1002999138018   # replace with main channel ID
# Temporary storage for thumbnails keyed by user_id
user_thumbnail = {}

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ---------------- /start COMMAND HANDLER ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /start <video_id>\nExample: /start 4")
        return

    video_id = context.args[0]
    context.user_data['video_id'] = int(video_id)

    await update.message.reply_text(
        f"✅ Please send me the custom thumbnail image for video ID {video_id} now."
    )

# ---------------- HANDLE THUMBNAIL IMAGE ----------------
async def handle_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_id = context.user_data.get('video_id')
    user_id = update.effective_user.id

    if not video_id:
        await update.message.reply_text("⚠️ Please send the /start command first with a video ID.")
        return

    if update.message.photo:
        photo = update.message.photo[-1]

        thumbnail_path = f"thumb_{user_id}_{video_id}.jpg"
        await photo.get_file().download_to_drive(thumbnail_path)

        user_thumbnail[user_id] = thumbnail_path

        await update.message.reply_text(f"✅ Custom thumbnail received. Forwarding video now, please wait...")

        await send_video_with_custom_thumb(update, context, video_id, thumbnail_path)

    else:
        await update.message.reply_text("⚠️ Please send an image (photo) as the thumbnail.")

# ---------------- FORWARD VIDEO WITH CUSTOM THUMBNAIL ----------------
async def send_video_with_custom_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE, video_id: int, thumb_path: str):
    try:
        # Inform user that forwarding has started
        await update.message.reply_text(f"⏳ Forwarding video ID {video_id}, please wait...")

        # Forward the message temporarily to get file_id
        msg = await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id=BACKUP_CHANNEL_ID,
            message_id=video_id
        )

        if msg.video:
            file_id = msg.video.file_id

            await context.bot.send_video(
                chat_id=MAIN_CHANNEL_ID,
                video=file_id,
                caption=msg.caption or "",
                thumb=open(thumb_path, 'rb')
            )

            # Cleanup: delete temp forwarded message
            try:
                await msg.delete()
            except:
                pass

            # Cleanup: remove thumbnail file
            os.remove(thumb_path)
            user_thumbnail.pop(update.effective_user.id, None)

            # Final confirmation to user
            await update.message.reply_text(f"✅ Video ID {video_id} has been forwarded successfully with your custom thumbnail.")

        else:
            await update.message.reply_text(f"❌ Message ID {video_id} is not a video.")

    except Exception as e:
        logging.error(f"Error forwarding video {video_id}: {e}")
        await update.message.reply_text(f"❌ Failed to forward video {video_id}: {e}")

# ---------------- MAIN FUNCTION ----------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_thumbnail))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
