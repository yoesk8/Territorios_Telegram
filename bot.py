import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- Google Sheets Setup ---
creds_json = os.getenv("GOOGLE_CREDENTIALS")
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

# --- Telegram Bot Setup ---
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Make sure you set this in Render environment variables

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Get first row from Google Sheet
    rows = sheet.get_all_records()
    first_row = rows[0] if rows else "Sheet is empty"
    await update.message.reply_text(f"Bot is running! First row: {first_row}")

# Build the bot application
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("test", test_command))

print("Bot is running...")

# Start the bot
app.run_polling()
