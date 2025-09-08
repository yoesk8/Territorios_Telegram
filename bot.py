import os
import json
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ------------------------------
# Google Sheets setup
# ------------------------------
creds_json = os.getenv("GOOGLE_CREDENTIALS")
if not creds_json:
    raise ValueError("GOOGLE_CREDENTIALS environment variable not set")

creds_dict = json.loads(creds_json)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("DoorToDoor_Territories").sheet1

# ------------------------------
# Telegram setup
# ------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set")

PORT = int(os.environ.get("PORT", 10000))  # Render provides this port
RENDER_URL = "https://territorios-telegram.onrender.com"

WEBHOOK_URL = f"{RENDER_URL}/webhook/{BOT_TOKEN}"

# ------------------------------
# Handlers
# ------------------------------
async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = sheet.get_all_records()
    first_row = rows[0] if rows else "Sheet is empty"
    await update.message.reply_text(f"Bot is running! First row: {first_row}")

# Add your other handlers here: /assign, /status, /complete
# Just copy the ones from your previous bot.py

# ------------------------------
# Application setup
# ------------------------------
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("test", test_command))
# Add your other handlers here

# ------------------------------
# Start the bot using webhooks
# ------------------------------
app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=WEBHOOK_URL
)
