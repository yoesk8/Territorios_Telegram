import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
from datetime import date, datetime, timedelta
import logging


# Logging config
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


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


from datetime import date, datetime, timedelta

def parse_sheet_date(raw_value):
    """Parse fecha de Google Sheets (string o serial). Devuelve date o None."""
    if not raw_value:
        return None

    if isinstance(raw_value, datetime):
        return raw_value.date()
    if isinstance(raw_value, date):
        return raw_value

    s = str(raw_value).strip()
    if s == "":
        return None

    # Serial Excel (número de días desde 1899-12-30)
    try:
        num = float(s)
        if num > 59:
            return (datetime(1899, 12, 30) + timedelta(days=int(num))).date()
    except Exception:
        pass

    # Quitar parte de hora si existe
    s_date_only = s.split(" ")[0].split("T")[0]

    # PROBAR PRIMERO DÍA/MES/AÑO (ajústalo según tu locale de Sheets)
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s_date_only, fmt).date()
        except Exception:
            continue

    return None



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

    # Estado actual (col 6) - case-insensitive
    current_status = sheet.cell(cell.row, 6).value
    normalized_status = (current_status or "").strip().lower()

    # Si ya está asignado o en progreso, parar
    if normalized_status in ("asignado", "en progreso"):
        await update.message.reply_text("Ese territorio ya ha sido asignado")
        return

    # Fecha de última finalización (col 5) con parse robusto
    last_completed_raw = sheet.cell(cell.row, 5).value
    logger.info(f"Valor crudo de col(5): {last_completed_raw}")
    last_completed_date = parse_sheet_date(last_completed_raw)
    logger.info(f"Valor parseado: {last_completed_date}")


    today = date.today()

    # Si se completó en la última semana → pedir confirmación con /si o /no
    if last_completed_date is not None:
        days_since = (today - last_completed_date).days
        logger.info(f"days_since:{days_since}")
        if 0 <= days_since <= 7:
            print(days_since, today)
            context.user_data["pending_assignment"] = {
                "territory_id": territory_id,
                "publisher": publisher,
                "row": cell.row
            }
            await update.message.reply_text(
                "⚠️ ADVERTENCIA! Este territorio se completó en la última semana, "
                "seguro que quieres asignarlo? Responde /si o /no"
            )
            return

    # Si no hay fecha o no es reciente → asignar de una
    await do_assignment(update, territory_id, publisher, cell.row)


async def do_assignment(update: Update, territory_id: str, publisher: str, row: int):
    today_str = date.today().isoformat()
    sheet.update_cell(row, 3, publisher)     # Col 3: asignado a
    sheet.update_cell(row, 4, today_str)     # Col 4: fecha de asignación
    sheet.update_cell(row, 6, "En progreso") # Col 6: estado

    await update.message.reply_text(
        f"✅ Territorio {territory_id} asignado a {publisher} hoy {today_str}, "
        "NO OLVIDES MARCARLO COMO COMPLETADO UNA VEZ TERMINADO 🙏. "
        "Puedes hacer esto usando el comando /completar"
    )


async def confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_assignment")
    if not pending:
        await update.message.reply_text("❌ No tienes ninguna asignación pendiente de confirmación")
        return

    await do_assignment(update, pending["territory_id"], pending["publisher"], pending["row"])
    context.user_data.pop("pending_assignment", None)


async def confirm_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pending_assignment" in context.user_data:
        context.user_data.pop("pending_assignment", None)
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
    if len(args) < 1:
        await update.message.reply_text(
            "Para usar este comando, la manera correcta de hacerlo es: "
            "/completar <numero_de_territorio>, Por ejemplo: /completar 1"
        )
        return

    territory_id = args[0]
    cell = sheet.find(territory_id)

    if not cell:
        await update.message.reply_text("❌ Territorio no encontrado")
        return

    today = date.today().isoformat()  # always YYYY-MM-DD

    # Update publisher & date completed
    sheet.update_cell(cell.row, 5, today)   # fecha en que se completó (col 5)
    sheet.update_cell(cell.row, 6, "Completado")  # status (col 6)

    await update.message.reply_text(
        f"✅ Territorio {territory_id} marcado como COMPLETADO el {today}"
    )

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
