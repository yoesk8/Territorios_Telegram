import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
import requests
from datetime import date, datetime, timedelta
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)



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
# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await update.message.reply_text("Hola! Bienvenido al asistente de Territorios para la congregación Puerto azul, para interactuar conmigo, puedes usar los siguientes comandos:\n /asignar --Este comando te permite asignar un territorio a un publicador-- \n /status --Este comando te permite saber si un territorio está actualmente asignado y a quien está asignado-- \n /completar --Este comando te permite marcar un territorio como completado-- \n /zona --Este comando te permite averiguar que territorios de una zona específica están asignados o no asignados")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📌 Asignar territorio", callback_data="menu_asignar"),
            InlineKeyboardButton("✅ Completar territorio", callback_data="menu_completar")
        ],
        [
            InlineKeyboardButton("🌍 Ver por zona", callback_data="menu_zona")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Bienvenido al gestor de territorios 👋\nElige una opción:", reply_markup=reply_markup)

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu_asignar":
        await query.edit_message_text("Selecciona un territorio para asignar (pendiente de implementar botones).")
    elif query.data == "menu_completar":
        await query.edit_message_text("Selecciona un territorio para completar (pendiente de implementar botones).")
    elif query.data == "menu_zona":
        # Reutilizamos lo que ya hicimos de zonas
        keyboard = [
            [
                InlineKeyboardButton("Puerto Azul", callback_data="zona_puertoazul"),
                InlineKeyboardButton("Puertas del Sol", callback_data="zona_puertasdelsol")
            ],
            [
                InlineKeyboardButton("Portete Tarqui", callback_data="zona_portetetarqui"),
                InlineKeyboardButton("Bosque Azul", callback_data="zona_bosqueazul")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🌍 Selecciona una zona:", reply_markup=reply_markup)


def set_webhook():
    url = f"{APP_URL}/{TOKEN}"
    webhook_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    response = requests.post(webhook_url, data={"url": url})
    print("Webhook setup response:", response.json())



# Función para parsear fechas de Google Sheets
def parse_sheet_date(raw_value):
    """Parsear fechas de Google Sheets (string o número serial) a date."""
    if not raw_value:
        return None

    # Si ya es date
    if isinstance(raw_value, date):
        return raw_value

    # Si es número serial
    if isinstance(raw_value, (int, float)):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=int(raw_value))).date()
        except Exception as e:
            logger.error(f"Error parseando número de fecha: {e}")
            return None

    raw_value = str(raw_value).strip()

    # Intentar múltiples formatos: día/mes/año, mes/día/año, año-mes-día
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw_value, fmt).date()
        except ValueError:
            continue

    logger.warning(f"No se pudo parsear la fecha: {raw_value}")
    return None

# Función principal de asignar
async def assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    logger.info(f"Comando /asignar recibido con args: {args}")

    if len(args) < 2:
        await update.message.reply_text(
            "Para usar este comando: /asignar <numero_de_territorio> <Persona>,por ejemplo: /asignar 1 Yoel"
        )
        return

    territory_id, publisher = args[0], args[1]
    logger.info(f"territory_id={territory_id}, publisher={publisher}")

    cell = sheet.find(territory_id)
    if not cell:
        await update.message.reply_text("❌ Territorio no encontrado")
        logger.info(f"Territorio {territory_id} no encontrado en la hoja")
        return

    # Status actual (col 6)
    current_status = sheet.cell(cell.row, 6).value
    normalized_status = (current_status or "").strip().lower()
    logger.info(f"Status actual: {current_status} → normalizado: {normalized_status}")

    # Fecha de última completación (col 5)
    last_completed_raw = sheet.cell(cell.row, 5).value
    last_completed_date = parse_sheet_date(last_completed_raw)
    logger.info(f"Valor crudo col(5): {last_completed_raw}, parseado: {last_completed_date}")

    today = date.today()
    logger.info(f"Fecha de hoy: {today}")

    # Validar si ya está asignado
    if normalized_status in ("asignado"):
        await update.message.reply_text("Ese territorio ya ha sido asignado")
        logger.info("No se asigna porque el status ya estaba en Asignado")
        return

    # Comprobar si se completó en la última semana
    if last_completed_date:
        diff_days = (today - last_completed_date).days
        logger.info(f"Días desde última completación: {diff_days}")
        if diff_days <= 7:
            context.user_data["pending_assignment"] = {
                "territory_id": territory_id,
                "publisher": publisher,
                "row": cell.row
            }
            await update.message.reply_text(
                "⚠️ ADVERTENCIA! Este territorio se completó en la última semana.\n"
                "Deseas asignarlo de todas maneras? Responde /si o /no"
            )
            logger.info(f"Asignación pendiente guardada: {context.user_data['pending_assignment']}")
            return

    # Asignación directa si no hay advertencia
    await do_assignment(update, territory_id, publisher, cell.row)
    logger.info(f"Territorio {territory_id} asignado directamente sin advertencia")

# Función para realizar la asignación
async def do_assignment(update, territory_id, publisher, row):
    today = date.today().isoformat()
    sheet.update_cell(row, 3, publisher)      # Col 3: asignado a
    sheet.update_cell(row, 4, today)          # Col 4: fecha asignación
    sheet.update_cell(row, 6, "Asignado")  # Col 6: status

    await update.message.reply_text(
        f"✅ Territorio {territory_id} asignado a {publisher} hoy {today}, "
        "NO OLVIDES MARCARLO COMO COMPLETADO 🙏. "
        "Usa /completar para finalizar"
    )

# Confirmación de asignación pendiente
async def confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_assignment")
    if not pending:
        await update.message.reply_text("❌ No hay ninguna asignación pendiente")
        return

    await do_assignment(update, pending["territory_id"], pending["publisher"], pending["row"])
    context.user_data.pop("pending_assignment")

async def confirm_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pending_assignment" in context.user_data:
        context.user_data.pop("pending_assignment")
        await update.message.reply_text("❌ Asignación cancelada.")
    else:
        await update.message.reply_text("❌ No hay ninguna asignación pendiente")




async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Este comando se usa asi: /status <# de territorio Ejemplo: /status 1>")
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
    sheet.update_cell(cell.row, 6, "No asignado")  # status (col 6)

    await update.message.reply_text(
        f"✅ Territorio {territory_id} se completó hoy: {today}"
    )

# async def zona(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     args = context.args
#     if len(args) < 2:
#         await update.message.reply_text(
#             "Para usar este comando: /zona <nombre_zona> <noasignados|asignados>\n"
#             "Ejemplo: /zona PuertoAzul noasignados"
#         )
#         return

#     # Normalizar zona y filtro
#     zona_name_input = args[0].lower().replace(" ", "")
#     filter_type = args[1].lower()

#     if filter_type not in ("noasignados", "asignados"):
#         await update.message.reply_text("El filtro debe ser 'noasignados' o 'asignados'.")
#         return

#     # Mapeo de nombres válidos de zonas
#     valid_zones = {
#         "puertoazul": "Puerto Azul",
#         "puertasdelsol": "Puertas del sol",
#         "portetetarqui": "Portete Tarqui",
#         "bosqueazul": "Bosque Azul"
#     }

#     if zona_name_input not in valid_zones:
#         await update.message.reply_text(
#             "Zona no válida. Zonas disponibles: Puerto Azul, Puertas del sol, Portete Tarqui, Bosque Azul."
#         )
#         return

#     zona_name = valid_zones[zona_name_input].lower().replace(" ", "")

#     rows = sheet.get_all_values()
#     matching_territories = []

#     for row in rows[1:]:  # saltar header
#         row_zone = row[1].lower().replace(" ", "")  # columna 2 = zona
#         status = (row[5] or "").strip().lower()    # columna 6 = estado

#         if row_zone != zona_name:
#             continue

#         if filter_type == "noasignados" and status not in ("asignado"):
#             matching_territories.append(row[0])
#         elif filter_type == "asignados" and status in ("asignado"):
#             matching_territories.append(row[0])

#     if not matching_territories:
#         await update.message.reply_text("No se encontraron territorios que cumplan con los criterios.")
#         return

#     # Limitar a 50 territorios para no saturar Telegram
#     max_items = 50
#     display_list = matching_territories[:max_items]
#     extra_count = len(matching_territories) - max_items

#     list_str = "\n".join(display_list)
#     msg = f"Territorios de la zona {valid_zones[zona_name_input]} ({filter_type}):\n{list_str}"
#     if extra_count > 0:
#         msg += f"\n...y {extra_count} más."

#     await update.message.reply_text(msg)

async def zona(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Puerto Azul", callback_data="zona_puertoazul"),
            InlineKeyboardButton("Puertas del Sol", callback_data="zona_puertasdelsol")
        ],
        [
            InlineKeyboardButton("Portete Tarqui", callback_data="zona_portetetarqui"),
            InlineKeyboardButton("Bosque Azul", callback_data="zona_bosqueazul")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Elige una zona:", reply_markup=reply_markup)

async def zona_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    zona_selected = query.data.replace("zona_", "")
    context.user_data["zona_selected"] = zona_selected

    # Ahora mostrar botones de filtro
    keyboard = [
        [
            InlineKeyboardButton("Asignados", callback_data="filtro_asignados"),
            InlineKeyboardButton("No Asignados", callback_data="filtro_noasignados")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=f"Zona seleccionada: {zona_selected.capitalize()}\nAhora elige un filtro:",
        reply_markup=reply_markup
    )

async def filtro_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    filtro_selected = query.data.replace("filtro_", "")
    zona_selected = context.user_data.get("zona_selected")

    if not zona_selected:
        await query.edit_message_text("❌ No se seleccionó ninguna zona.")
        return

    # Aquí reutilizas la lógica que ya tienes para filtrar territorios
    rows = sheet.get_all_values()
    matching_territories = []
    for row in rows[1:]:
        row_zone = row[1].lower().replace(" ", "")
        status = (row[5] or "").strip().lower()

        if row_zone != zona_selected:
            continue

        if filtro_selected == "noasignados" and status not in ("asignado", "en progreso"):
            matching_territories.append(row[0])
        elif filtro_selected == "asignados" and status in ("asignado", "en progreso"):
            matching_territories.append(row[0])

    if not matching_territories:
        await query.edit_message_text("No se encontraron territorios que cumplan con los criterios.")
        return

    # Mostrar lista
    max_items = 50
    display_list = matching_territories[:max_items]
    extra_count = len(matching_territories) - max_items
    list_str = "\n".join(display_list)

    msg = f"📍 Territorios de {zona_selected.capitalize()} ({filtro_selected}):\n{list_str}"
    if extra_count > 0:
        msg += f"\n...y {extra_count} más."

    await query.edit_message_text(msg)



# --- Main ---
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("inicio", start))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(zona_callback, pattern="^zona_"))
    application.add_handler(CallbackQueryHandler(filtro_callback, pattern="^filtro_"))
    application.add_handler(CommandHandler("asignar", assign))
    application.add_handler(CommandHandler("si", confirm_yes))
    application.add_handler(CommandHandler("no", confirm_no))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("completar", complete))
    application.add_handler(CommandHandler("zona", zona))
    application.add_handler(CallbackQueryHandler(zona_callback, pattern="^zona_"))
    application.add_handler(CallbackQueryHandler(filtro_callback, pattern="^filtro_"))



    set_webhook()
    application.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 10000)),
    url_path=TOKEN,  # 👈 listen at /<TOKEN>
    webhook_url=f"{APP_URL}/{TOKEN}"  # 👈 matches Telegram webhook
)


if __name__ == "__main__":
    main()
