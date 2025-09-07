import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime
from telegram.ext import CommandHandler

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

async def assign_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Command format: /assign <territory> <team>
        territory = context.args[0]
        team = context.args[1]
        
        # Find the row with the territory
        cell = sheet.find(territory)
        row_number = cell.row

        # Update Assigned To and Assigned Date
        sheet.update_cell(row_number, 3, team)  # Assigned To
        sheet.update_cell(row_number, 4, datetime.today().strftime("%Y-%m-%d"))  # Assigned Date
        sheet.update_cell(row_number, 5, "In Progress")  # Status

        await update.message.reply_text(f"Territory {territory} assigned to {team}!")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# Build the bot application
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("asignar", assign_command))

print("Bot is running...")

# Start the bot
app.run_polling()
