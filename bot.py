import os
import json
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ==============================
# Google Sheets Setup
# ==============================
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

sheet = client.open("DoorToDoor_Territories").sheet1  # Make sure sheet name matches

# ==============================
# Telegram Bot Setup
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set")

PORT = int(os.environ.get("PORT", 10000))  # Render provides this

# Hardcode your Render service URL here
RENDER_URL = "https://your-service-name.onrender.com"  # <- Replace with your Render URL
WEBHOOK_URL = f"{RENDER_URL}/webhook/{BOT_TOKEN}"

# ==============================
# Command Handlers
# ==============================
async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = sheet.get_all_records()
    first_row = rows[0] if rows else "Sheet is empty"
    await update.message.reply_text(f"Bot is running! First row: {first_row}")

async def assign_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        territory = context.args[0]
        team = context.args[1]

        cell = sheet.find(territory)
        row_number = cell.row

        current_assigned = sheet.cell(row_number, 3).value
        notes = sheet.cell(row_number, 6).value or ""
        if current_assigned:
            await update.message.reply_text(f"Territory {territory} is already assigned to {current_assigned}")
            return
        if "no visit" in notes.lower():
            await update.message.reply_text(f"Territory {territory} is marked as 'Do Not Visit'. Cannot assign.")
            return

        sheet.update_cell(row_number, 3, team)
        sheet.update_cell(row_number, 4, datetime.today().strftime("%Y-%m-%d"))
        sheet.update_cell(row_number, 5, "In Progress")

        await update.message.reply_text(f"Territory {territory} assigned to {team}!")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        territory = context.args[0]
        cell = sheet.find(territory)
        row_number = cell.row

        assigned_to = sheet.cell(row_number, 3).value
        status = sheet.cell(row_number, 5).value
        notes = sheet.cell(row_number, 6).value

        msg = f"Territory {territory}\nAssigned to: {assigned_to or 'None'}\nStatus: {status or 'None'}\nNotes: {notes or 'None'}"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def complete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        territory = context.args[0]
        cell = sheet.find(territory)
        row_number = cell.row

        sheet.update_cell(row_number, 5, "Completed")
        await update.message.reply_text(f"Territory {territory} marked as Completed!")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# ==============================
# Build the bot application
# ==============================
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("test", test_command))
app.add_handler(CommandHandler("assign", assign_command))
app.add_handler(CommandHandler("status", status_command))
app.add_handler(CommandHandler("complete", complete_command))

# ==============================
# Run the bot using Webhook
# ==============================
app.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    webhook_url=WEBHOOK_URL
)
