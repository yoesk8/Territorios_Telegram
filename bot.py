import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Load environment variables ---
TOKEN = os.environ["BOT_TOKEN"]
APP_URL = "https://territorios-telegram.onrender.com"

# Google credentials are stored as JSON in an env variable
google_creds_json = os.environ.get("GOOGLE_CREDENTIALS")
if not google_creds_json:
    raise RuntimeError("GOOGLE_CREDENTIALS not set in environment!")

creds_dict = json.loads(google_creds_json)

# --- Connect to Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("DoorToDoor_Territories").sheet1

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚪 Territory Bot is alive! Use /assign /status /complete")

async def assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /assign <territory_id> <team>")
        return

    territory_id, team = args[0], args[1]
    cell = sheet.find(territory_id)
    if cell:
        sheet.update_cell(cell.row, 3, "Assigned")
        sheet.update_cell(cell.row, 4, team)
        sheet.update_cell(cell.row, 5, "In Progress")
        await update.message.reply_text(f"✅ Territory {territory_id} assigned to {team}")
    else:
        await update.message.reply_text("❌ Territory not found")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /status <territory_id>")
        return

    territory_id = args[0]
    cell = sheet.find(territory_id)
    if cell:
        row = sheet.row_values(cell.row)
        await update.message.reply_text(f"📊 Status of {territory_id}: {row}")
    else:
        await update.message.reply_text("❌ Territory not found")

async def complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /complete <territory_id>")
        return

    territory_id = args[0]
    cell = sheet.find(territory_id)
    if cell:
        sheet.update_cell(cell.row, 5, "Completed")
        sheet.update_cell(cell.row, 6, str(update.message.date))
        await update.message.reply_text(f"🎉 Territory {territory_id} marked as Completed")
    else:
        await update.message.reply_text("❌ Territory not found")

# --- Main ---
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("assign", assign))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("complete", complete))

    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        webhook_url=f"{APP_URL}/webhook/{TOKEN}"
    )

if __name__ == "__main__":
    main()
