import logging
import asyncio
from datetime import time, datetime
from zoneinfo import ZoneInfo
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, Defaults
import os
import re

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

ALLOWED_USERNAME = 'jaredtanzd'

SET_MESSAGE, SET_TIME, CONFIRM = range(3)

scheduled_job = None
message_template = ""
message_time = None
increment_counter = None
decrement_counter = None

def parse_custom_message(template):
    global increment_counter, decrement_counter
    message = template
    
    if increment_counter is not None:
        message = re.sub(r'{increment,\s*\d+}', str(increment_counter), message)

    if decrement_counter is not None:
        message = re.sub(r'{decrement,\s*\d+}', str(decrement_counter), message)

    return message

def update_counters():
    global increment_counter, decrement_counter
    if increment_counter is not None:
        increment_counter += 1
    if decrement_counter is not None:
        decrement_counter -= 1

def check_user(update: Update) -> bool:
    return update.message.from_user.username == ALLOWED_USERNAME

async def create_scheduled_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not check_user(update):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    await update.message.reply_text("Let's create a scheduled message. First, please enter the custom message you want to send daily.")
    return SET_MESSAGE

async def set_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not check_user(update):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    global message_template, increment_counter, decrement_counter
    message_template = update.message.text

    increment_match = re.search(r'{increment,\s*(\d+)}', message_template)
    decrement_match = re.search(r'{decrement,\s*(\d+)}', message_template)

    if increment_match:
        increment_counter = int(increment_match.group(1))

    if decrement_match:
        decrement_counter = int(decrement_match.group(1))

    await update.message.reply_text("Message set. Now, please specify the time for the daily message (in 24-hour format, e.g., 14:30 for 2:30 PM).")
    return SET_TIME

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not check_user(update):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    global message_time
    try:
        hour, minute = map(int, update.message.text.split(':'))
        message_time = time(hour=hour, minute=minute, tzinfo=ZoneInfo("Asia/Singapore"))
        preview_message = parse_custom_message(message_template)
        await update.message.reply_text(f"Your message will be sent daily at {hour:02d}:{minute:02d} Singapore time.\n\nHere's a preview of your message:\n\n{preview_message}\n\nIs this correct? (Yes/No)")
        return CONFIRM
    except ValueError:
        await update.message.reply_text("Invalid time format. Please use HH:MM (24-hour format).")
        return SET_TIME

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not check_user(update):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    if update.message.text.lower() == 'yes':
        global scheduled_job
        if scheduled_job:
            scheduled_job.schedule_removal()

        scheduled_job = context.job_queue.run_daily(
            send_scheduled_message, 
            time=message_time,
            chat_id=update.effective_chat.id
        )
        logger.info(f"Scheduled job: {scheduled_job}")

        await update.message.reply_text("Scheduled message has been set up successfully!")
        return ConversationHandler.END
    elif update.message.text.lower() == 'no':
        await update.message.reply_text("Let's start over. Please enter your custom message.")
        return SET_MESSAGE
    else:
        await update.message.reply_text("Please respond with 'Yes' or 'No'.")
        return CONFIRM

async def send_scheduled_message(context: ContextTypes.DEFAULT_TYPE):
    global message_template

    logger.info(f"Job executed at {datetime.now(ZoneInfo('Asia/Singapore'))} Singapore time")

    update_counters()
    message_to_send = parse_custom_message(message_template)

    job = context.job if context.job else None
    chat_id = job.chat_id if job else context._chat_id

    await context.bot.send_message(chat_id=chat_id, text=message_to_send)
    logger.info(f"Scheduled message sent: {message_to_send}")

async def stop_scheduled_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    global scheduled_job
    if scheduled_job:
        scheduled_job.schedule_removal()
        scheduled_job = None
        await update.message.reply_text("Scheduled message has been stopped.")
        logger.info("Scheduled message stopped")
    else:
        await update.message.reply_text("There is no active scheduled message.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not check_user(update):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def trigger_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    await send_scheduled_message(context)
    await update.message.reply_text("Scheduled job triggered manually.")
    logger.info("Scheduled job triggered manually")

async def set_commands(application: Application):
    commands = [
        BotCommand("create_scheduled_message", "Create a new scheduled message"),
        BotCommand("stop_scheduled_message", "Stop the current scheduled message"),
        BotCommand("trigger_job", "Trigger the scheduled job manually for testing")
    ]
    await application.bot.set_my_commands(commands)

async def main() -> None:
    defaults = Defaults(tzinfo=ZoneInfo("Asia/Singapore"))
    application = Application.builder().token(TOKEN).defaults(defaults).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('create_scheduled_message', create_scheduled_message)],
        states={
            SET_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_message)],
            SET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_time)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("stop_scheduled_message", stop_scheduled_message))
    application.add_handler(CommandHandler("trigger_job", trigger_job))

    await set_commands(application)

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    print("Bot is running. Press Ctrl-C to stop.")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Bot is shutting down...")
    finally:
        await application.stop()

if __name__ == '__main__':
    asyncio.run(main())
