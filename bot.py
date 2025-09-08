import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
from datetime import date

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
    await update.message.reply_text("Hola! Bienvenido al asistente de Territorios para la congregación Puerto azul, para interactuar conmigo, puedes usar los siguientes comandos: /asignar /status /completar")


def set_webhook():
    url = f"{APP_URL}/{TOKEN}"
    webhook_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    response = requests.post(webhook_url, data={"url": url})
    print("Webhook setup response:", response.json())

async def assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Para usar este comando, la manera correcta de hacerlo es: /asignar <numero_de_territorio> <Persona>, Por ejemplo: /asignar 1 Yoel")
        return

    territory_id, publisher = args[0], args[1]
    cell = sheet.find(territory_id)
    today = date.today().isoformat()
    if cell:
        sheet.update_cell(cell.row, 3, publisher)
        sheet.update_cell(cell.row, 4, today)
        sheet.update_cell(cell.row, 6, "En progreso")
        await update.message.reply_text(f"✅ Territorio {territory_id} asignado a {publisher} hoy {today}, NO OLVIDES MARCARLO COMO COMPLETADO UNA VEZ TERMINADO 🙏. Puedes hacer esto usando el comando /completar")
    else:
        await update.message.reply_text("❌ Territorio no encontrado")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /status <territory_id>")
        return

    territory_id = args[0]
    cell = sheet.find(territory_id)
    if cell:
        row = sheet.row_values(cell.row)
        await update.message.reply_text(f"El Territorio # {territory_id} se encuentra {row}")
    else:
        await update.message.reply_text("❌ Territorio no encontrado")

async def complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /complete <territory_id>")
        return

    territory_id = args[0]
    cell = sheet.find(territory_id)
    if cell:
        sheet.update_cell(cell.row, 5, "Completado!")
        sheet.update_cell(cell.row, 6, str(update.message.date))
        await update.message.reply_text(f"🎉 Territorio {territory_id} registrado como completado")
    else:
        await update.message.reply_text("❌ Territorio no encontrado")

# --- Main ---
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("inicio", start))
    application.add_handler(CommandHandler("asignar", assign))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("completar", complete))

    set_webhook()
    application.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 10000)),
    url_path=TOKEN,  # 👈 listen at /<TOKEN>
    webhook_url=f"{APP_URL}/{TOKEN}"  # 👈 matches Telegram webhook
)


if __name__ == "__main__":
    main()
