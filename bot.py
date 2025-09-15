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
        file = await photo.get_file()
        await file.download_to_drive(custom_path=thumbnail_path)

        user_thumbnail[user_id] = thumbnail_path

        await update.message.reply_text(f"✅ Custom thumbnail received. Forwarding video now, please wait...")

        await send_video_auto_thumbnail(update, context, video_id)

    else:
        await update.message.reply_text("⚠️ Please send an image (photo) as the thumbnail.")

# ---------------- SEND VIDEO WITH AUTO-GENERATED THUMBNAIL ----------------
async def send_video_auto_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE, video_id: int):
    try:
        await update.message.reply_text(f"⏳ Downloading video ID {video_id}, please wait...")

        # Step 1: Forward video temporarily
        msg = await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id=BACKUP_CHANNEL_ID,
            message_id=video_id
        )

        if msg.video:
            file_id = msg.video.file_id
            file = await context.bot.get_file(file_id)

            video_path = f"video_{video_id}.mp4"
            await file.download_to_drive(custom_path=video_path)

            await update.message.reply_text(f"✅ Video downloaded. Uploading without custom thumbnail now...")

            # Step 2: Send video WITHOUT custom thumbnail (auto-generated)
            await context.bot.send_video(
                chat_id=MAIN_CHANNEL_ID,
                video=open(video_path, 'rb'),
                caption=msg.caption or ""
            )

            # Cleanup
            try:
                await msg.delete()
            except:
                pass

            os.remove(video_path)
            thumb_path = user_thumbnail.pop(update.effective_user.id, None)
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)

            await update.message.reply_text(f"✅ Video ID {video_id} forwarded successfully with auto-generated thumbnail.")

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
