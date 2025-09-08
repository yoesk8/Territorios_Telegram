import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
from datetime import date, datetime, timedelta

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

from datetime import date


async def assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Para usar este comando, la manera correcta de hacerlo es: "
            "/asignar <numero_de_territorio> <Persona>, Por ejemplo: /asignar 1 Yoel"
        )
        return

    territory_id, publisher = args[0], args[1]
    cell = sheet.find(territory_id)

    if not cell:
        await update.message.reply_text("❌ Territorio no encontrado")
        return

    # Get current status (col 6)
    current_status = sheet.cell(cell.row, 6).value
    normalized_status = (current_status or "").strip().lower()

    # Get last completion date (col 5)
    last_completed_raw = sheet.cell(cell.row, 5).value
    last_completed_date = None
    if last_completed_raw:
        try:
            last_completed_date = datetime.strptime(last_completed_raw, "%Y-%m-%d").date()
        except ValueError:
            pass  # Ignore parsing errors if the sheet has a weird format

    today = date.today()

    # If already assigned, stop
    if normalized_status in ("asignado", "en progreso"):
        await update.message.reply_text("Ese territorio ya ha sido asignado")
        return

    # If completed within the last 7 days → ask for confirmation
    if last_completed_date and (today - last_completed_date).days <= 7:
        context.user_data["pending_assignment"] = {
            "territory_id": territory_id,
            "publisher": publisher,
            "row": cell.row
        }
        await update.message.reply_text(
            "⚠️ ADVERTENCIA! Este territorio se completó en la última semana.\n\n"
            "¿Seguro que quieres asignarlo?\n"
            "Responde /si o /no"
        )
        return

    # Otherwise → assign immediately
    await do_assignment(update, territory_id, publisher, cell.row)


async def do_assignment(update, territory_id, publisher, row):
    today = date.today().isoformat()
    sheet.update_cell(row, 3, publisher)
    sheet.update_cell(row, 4, today)
    sheet.update_cell(row, 6, "En progreso")

    await update.message.reply_text(
        f"✅ Territorio {territory_id} asignado a {publisher} hoy {today}, "
        "NO OLVIDES MARCARLO COMO COMPLETADO UNA VEZ TERMINADO 🙏. "
        "Puedes hacer esto usando el comando /completar"
    )


async def confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_assignment")
    if not pending:
        await update.message.reply_text("❌ No tienes ninguna asignación pendiente de confirmación")
        return

    await do_assignment(update, pending["territory_id"], pending["publisher"], pending["row"])
    context.user_data.pop("pending_assignment")


async def confirm_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pending_assignment" in context.user_data:
        context.user_data.pop("pending_assignment")
        await update.message.reply_text("❌ Asignación cancelada.")
    else:
        await update.message.reply_text("❌ No tienes ninguna asignación pendiente de confirmación")


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
    application.add_handler(CommandHandler("si", confirm_yes))
    application.add_handler(CommandHandler("no", confirm_no))
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
