import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from datetime import date, datetime, timedelta
import logging
import requests

# Logging config
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Load environment variables ---
TOKEN = os.environ["BOT_TOKEN"]
APP_URL = "https://territorios-telegram.onrender.com"

google_creds_json = os.environ.get("GOOGLE_CREDENTIALS")
if not google_creds_json:
    raise RuntimeError("GOOGLE_CREDENTIALS not set in environment!")

creds_dict = json.loads(google_creds_json)

# --- Connect to Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("DoorToDoor_Territories").sheet1

# --- Utilidades ---
def parse_sheet_date(raw_value):
    """Parsear fechas de Google Sheets a date."""
    if not raw_value:
        return None
    if isinstance(raw_value, date):
        return raw_value
    if isinstance(raw_value, (int, float)):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=int(raw_value))).date()
        except:
            return None
    raw_value = str(raw_value).strip()
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw_value, fmt).date()
        except ValueError:
            continue
    return None

def normalize_zone_name(name: str) -> str:
    """Normaliza nombres de zona para comparar con la hoja."""
    return name.lower().replace(" ", "")


# --- Main menu ---
async def inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📍 Zonas", callback_data="menu_zona")],
        [InlineKeyboardButton("📝 Asignar", callback_data="menu_asignar")],
        [InlineKeyboardButton("✅ Completar", callback_data="menu_completar")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text("📌 Menú principal:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text("📌 Menú principal:", reply_markup=reply_markup)
        await update.callback_query.answer()


# --- Menu handler ---
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # Zonas submenu
    if data == "menu_zona":
        keyboard = [
            [InlineKeyboardButton("Puerto Azul", callback_data="zona_puertoazul")],
            [InlineKeyboardButton("Puertas del Sol", callback_data="zona_puertasdelsol")],
            [InlineKeyboardButton("Portete Tarqui", callback_data="zona_portetetarqui")],
            [InlineKeyboardButton("Bosque Azul", callback_data="zona_bosqueazul")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="menu_inicio")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("🌍 Selecciona una zona:", reply_markup=reply_markup)

    # Asignar submenu
    elif data == "menu_asignar":
        await asignar_menu(update, context)

    # Completar submenu
    elif data == "menu_completar":
        await completar_menu(update, context)


# --- Asignación de territorios ---
async def asignar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    zonas = ["Puerto Azul", "Puertas del Sol", "Portete Tarqui", "Bosque Azul"]
    buttons = [[InlineKeyboardButton(z, callback_data=f"asignar_zona_{normalize_zone_name(z)}")] for z in zonas]
    buttons.append([InlineKeyboardButton("⬅️ Volver", callback_data="menu_inicio")])
    reply_markup = InlineKeyboardMarkup(buttons)

    text = "🌍 Selecciona la zona de la que quieres asignar un territorio:"
    if query:
        await query.message.edit_text(text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

async def asignar_zona_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    zona_selected = query.data.replace("asignar_zona_", "")
    context.user_data["zona_selected"] = zona_selected

    rows = sheet.get_all_values()
    buttons = []
    for row in rows[1:]:
        territory_id = row[0]
        row_zone = normalize_zone_name(row[1])
        status = (row[5] or "").strip().lower()

        if row_zone == zona_selected and status not in ("asignado", "en progreso"):
            buttons.append([InlineKeyboardButton(territory_id, callback_data=f"asignar_territorio_{territory_id}")])

    if not buttons:
        await query.message.edit_text(f"No hay territorios disponibles en {zona_selected.capitalize()}.")
        return

    buttons.append([InlineKeyboardButton("⬅️ Volver", callback_data="menu_asignar")])
    reply_markup = InlineKeyboardMarkup(buttons)
    await query.message.edit_text(f"📍 Territorios disponibles en {zona_selected.capitalize()}:", reply_markup=reply_markup)

async def asignar_territorio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    territory_id = query.data.replace("asignar_territorio_", "")
    cell = sheet.find(territory_id)
    if not cell:
        await query.message.edit_text("❌ Territorio no encontrado")
        return

    current_status = (sheet.cell(cell.row, 6).value or "").strip().lower()
    last_completed_date = parse_sheet_date(sheet.cell(cell.row, 5).value)
    today = date.today()

    if current_status in ("asignado"):
        await query.message.edit_text("Ese territorio ya ha sido asignado")
        return

    context.user_data["pending_assignment"] = {"territory_id": territory_id, "row": cell.row}

    if last_completed_date and (today - last_completed_date).days <= 7:
        buttons = [
            [InlineKeyboardButton("✅ Sí, asignar de todas maneras", callback_data="confirm_si")],
            [InlineKeyboardButton("❌ No, cancelar", callback_data="confirm_no")],
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            "⚠️ ADVERTENCIA! Este territorio se completó en la última semana.\n"
            "¿Deseas asignarlo de todas maneras?",
            reply_markup=reply_markup
        )
        return

    await mostrar_botones_personas(query, context)


# Logica para completar territorio
async def completar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    assigned_cells = sheet.findall("Asignado", in_column=6)

    if not assigned_cells:
        await query.message.edit_text("No hay territorios asignados ✅")
        await query.answer()
        return

    keyboard = []
    for cell in assigned_cells:
        territory_id = sheet.cell(cell.row, 1).value  # col 1 = territory ID
        keyboard.append([
            InlineKeyboardButton(
                f"Completar {territory_id}",
                callback_data=f"completar_{territory_id}"
            )
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="menu_inicio")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("Selecciona el territorio a completar:", reply_markup=reply_markup)
    await query.answer()

async def completar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    territory_id = data.split("_", 1)[1]

    await query.answer()  # stop spinner immediately

    cell = sheet.find(territory_id)
    if not cell:
        await query.message.edit_text("❌ Territorio no encontrado")
        return

    today = date.today().isoformat()
    sheet.update_cell(cell.row, 5, today)   # Col 5 = Fecha completado
    sheet.update_cell(cell.row, 6, "No asignado")

    await query.message.edit_text(f"✅ Territorio {territory_id} completado hoy: {today}")


async def confirm_si_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get("pending_assignment")
    if not pending:
        await query.message.edit_text("❌ No hay ninguna asignación pendiente")
        return

    await mostrar_botones_personas(query, context)

async def confirm_no_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_assignment", None)
    await query.message.edit_text("❌ Asignación cancelada.")

async def mostrar_botones_personas(query, context):
    publishers = ["Yoel", "Ana", "Carlos"]
    buttons = [[InlineKeyboardButton(p, callback_data=f"asignar_persona_{p}")] for p in publishers]
    buttons.append([InlineKeyboardButton("⬅️ Volver", callback_data="menu_asignar")])
    reply_markup = InlineKeyboardMarkup(buttons)

    pending = context.user_data.get("pending_assignment")
    await query.message.edit_text(
        f"Territorio {pending['territory_id']} seleccionado. Elige la persona a asignar:",
        reply_markup=reply_markup
    )

async def asignar_persona_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    person = query.data.replace("asignar_persona_", "")
    pending = context.user_data.get("pending_assignment")
    if not pending:
        await query.message.edit_text("❌ No hay territorio pendiente para asignar.")
        return

    row = pending["row"]
    await do_assignment(query, pending["territory_id"], person, row)
    context.user_data.pop("pending_assignment")

async def do_assignment(update_or_query, territory_id, publisher, row):
    today = date.today().isoformat()
    sheet.update_cell(row, 3, publisher)
    sheet.update_cell(row, 4, today)
    sheet.update_cell(row, 6, "Asignado")

    # Leer la nota en la columna 7
    nota = sheet.cell(row, 7).value

    text = (
        f"✅ Territorio {territory_id} asignado a {publisher} hoy {today}, "
        "NO OLVIDES MARCARLO COMO COMPLETADO 🙏. Una vez que hayas completado puedes usar /completar para finalizar"
    )

    # Si hay nota, agregar advertencia
    if nota:
        text += f"\n\n⚠️ *¡ADVERTENCIA!* El territorio {territory_id} tiene la siguiente Nota:\n_{nota}_"

    # Enviar mensaje según si viene de un mensaje o de un callback
    if hasattr(update_or_query, "message"):
        await update_or_query.message.reply_text(text, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(text, parse_mode="Markdown")


# --- Status y completar ---
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Uso: /status <# de territorio>")
        return

    territory_id = args[0]
    cell = sheet.find(territory_id)
    if cell:
        row = sheet.row_values(cell.row)
        await update.message.reply_text(f"Territorio #{territory_id}: {row}")
    else:
        await update.message.reply_text("❌ Territorio no encontrado")

async def complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Uso correcto: /completar <# de territorio>")
        return

    territory_id = args[0]
    cell = sheet.find(territory_id)
    if not cell:
        await update.message.reply_text("❌ Territorio no encontrado")
        return

    today = date.today().isoformat()
    sheet.update_cell(cell.row, 5, today)
    sheet.update_cell(cell.row, 6, "No asignado")

    await update.message.reply_text(f"✅ Territorio {territory_id} completado hoy: {today}")

# --- Zonas y filtros ---

async def zona_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    zona_selected = query.data.replace("zona_", "")
    context.user_data["zona_selected"] = zona_selected

    keyboard = [
        [InlineKeyboardButton("Asignados", callback_data="filtro_asignados"),
         InlineKeyboardButton("No Asignados", callback_data="filtro_noasignados")]
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

    rows = sheet.get_all_values()
    matching_territories = []
    for row in rows[1:]:
        row_zone = normalize_zone_name(row[1])
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

    max_items = 50
    display_list = matching_territories[:max_items]
    extra_count = len(matching_territories) - max_items
    list_str = "\n".join(display_list)
    msg = f"📍 Territorios de {zona_selected.capitalize()} ({filtro_selected}):\n{list_str}"
    if extra_count > 0:
        msg += f"\n...y {extra_count} más."
    await query.edit_message_text(msg)

# --- Webhook ---
def set_webhook():
    url = f"{APP_URL}/{TOKEN}"
    webhook_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    response = requests.post(webhook_url, data={"url": url})
    print("Webhook setup response:", response.json())

# --- Main ---
def main():
    application = Application.builder().token(TOKEN).build()

    # Comandos
    application.add_handler(CommandHandler("inicio", inicio))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("completar", complete))

    # --- MENÚS PRINCIPALES ---
    # Cualquier callback que empiece con "menu_" lo maneja menu_handler
    application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_"))

    # --- ASIGNACIÓN ---
    application.add_handler(CallbackQueryHandler(asignar_zona_callback, pattern="^asignar_zona_"))
    application.add_handler(CallbackQueryHandler(asignar_territorio_callback, pattern="^asignar_territorio_"))
    application.add_handler(CallbackQueryHandler(asignar_persona_callback, pattern="^asignar_persona_"))
    application.add_handler(CallbackQueryHandler(confirm_si_callback, pattern="^confirm_si$"))
    application.add_handler(CallbackQueryHandler(confirm_no_callback, pattern="^confirm_no$"))

    # --- ZONAS Y FILTROS ---
    application.add_handler(CallbackQueryHandler(zona_callback, pattern="^zona_"))
    application.add_handler(CallbackQueryHandler(filtro_callback, pattern="^filtro_"))


    # Completar
    application.add_handler(CallbackQueryHandler(completar_callback, pattern="^completar_"))


    # Menú principal
    application.add_handler(CallbackQueryHandler(menu_handler, pattern="^menu_inicio$"))

    # Webhook
    set_webhook()
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        url_path=TOKEN,
        webhook_url=f"{APP_URL}/{TOKEN}"
    )


if __name__ == "__main__":
    main()
