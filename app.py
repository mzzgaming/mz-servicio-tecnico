import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template
import gspread
from google.oauth2.service_account import Credentials
import requests

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))

# ─── USUARIOS ─────────────────────────────────────────────────────────────────
ADMIN_IDS = {909301871, 8832743374}  # Martin y MZ Gaming (admins)

TECHNICIANS = {
    909301871: "Martin",
    8832743374: "Mz Gaming",
}

ALL_CHAT_IDS = list(TECHNICIANS.keys())

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SHEET_ID          = os.environ.get("SHEET_ID", "")
BUSINESS_SHEET_ID = os.environ.get("BUSINESS_SHEET_ID", "1FHEBuzVEkpg_w8dDMP_Y1YeZBtUprtG9")
BOT_TOKEN         = os.environ.get("BOT_TOKEN", "")
WEBHOOK_SECRET    = os.environ.get("WEBHOOK_SECRET", "mzgaming2024")

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# ─── GOOGLE SHEETS ─────────────────────────────────────────────────────────────
def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def get_next_order_id(sheet):
    records = sheet.get_all_records()
    if not records:
        return "ORD-001"
    last_id = records[-1].get("ID", "ORD-000")
    try:
        num = int(last_id.split("-")[1]) + 1
    except:
        num = len(records) + 1
    return f"ORD-{num:03d}"

# ─── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_telegram(chat_id, text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json()
    except Exception:
        return {}

def broadcast(text, exclude=None):
    """Manda mensaje a todos los técnicos."""
    for chat_id in ALL_CHAT_IDS:
        if exclude and chat_id == exclude:
            continue
        send_telegram(chat_id, text)

def set_webhook(base_url):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    webhook_url = f"{base_url}/webhook/{WEBHOOK_SECRET}"
    requests.post(url, json={"url": webhook_url})

# ─── RUTAS WEB ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/orders")
def orders_page():
    return render_template("orders.html")

@app.route("/api/orders", methods=["GET"])
def get_orders():
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        return jsonify({"ok": True, "orders": records})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/orders/<order_id>", methods=["PATCH"])
def update_order(order_id):
    try:
        data    = request.json
        sheet   = get_sheet()
        records = sheet.get_all_records()
        for i, row in enumerate(records, start=2):
            if row.get("ID", "").upper() == order_id.upper():
                if "importe" in data:
                    sheet.update_cell(i, 12, str(data["importe"]).strip())
                if "estado_pago" in data:
                    sheet.update_cell(i, 13, str(data["estado_pago"]).strip())
                return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Orden no encontrada"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/orders", methods=["POST"])
def create_order():
    try:
        data = request.json
        sheet = get_sheet()

        order_id    = get_next_order_id(sheet)
        cliente     = data.get("cliente", "").strip()
        componentes = data.get("componentes", "").strip()
        trabajo     = data.get("trabajo", "").strip()
        fecha       = data.get("fecha", "").strip()
        prioridad   = data.get("prioridad", "Normal").strip()
        notas        = data.get("notas", "").strip()
        importe      = data.get("importe", "").strip()
        estado_pago  = data.get("estado_pago", "Pendiente").strip()
        created_at   = datetime.now().strftime("%d/%m/%Y %H:%M")

        row = [order_id, cliente, componentes, trabajo, fecha,
               prioridad, notas, "🟡 Pendiente", "", created_at, "", importe, estado_pago]
        sheet.append_row(row)

        prioridad_emoji = {"Alta": "🔴", "Normal": "🟡", "Baja": "🟢"}.get(prioridad, "🟡")
        msg = (
            f"🔧 *Nueva orden de trabajo*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 *ID:* `{order_id}`\n"
            f"👤 *Cliente:* {cliente}\n"
            f"🖥️ *Componentes:* {componentes}\n"
            f"🛠️ *Trabajo:* {trabajo}\n"
            f"📅 *Entrega:* {fecha}\n"
            f"{prioridad_emoji} *Prioridad:* {prioridad}\n"
        )
        if notas:
            msg += f"📝 *Notas:* {notas}\n"
        msg += f"\nPara marcar como lista: `/lista {cliente}`\nVer todos los comandos: /ayuda"

        broadcast(msg)

        return jsonify({"ok": True, "order_id": order_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── WEBHOOK TELEGRAM ──────────────────────────────────────────────────────────
@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):
    if secret != WEBHOOK_SECRET:
        return "Unauthorized", 401

    update  = request.json
    message = update.get("message", {})
    text    = message.get("text", "").split("@")[0]  # strip @botname suffix in groups
    chat_id = message.get("chat", {}).get("id")
    user_id = int(message.get("from", {}).get("id", 0))
    user    = TECHNICIANS.get(user_id, message.get("from", {}).get("first_name", "Técnico"))
    is_admin = (user_id in ADMIN_IDS)

    if user_id not in TECHNICIANS:
        return jsonify({"ok": True})

    # ── /lista <nombre cliente> ─────────────────────────────────────────────
    if text.startswith("/lista "):
        nombre = text.split(" ", 1)[1].strip()
        try:
            sheet   = get_sheet()
            records = sheet.get_all_records()
            found   = False
            for i, row in enumerate(records, start=2):
                if row.get("Cliente", "").lower() == nombre.lower() and "Pendiente" in row.get("Estado", ""):
                    found = True
                    order_id = row.get("ID", "")
                    now = datetime.now().strftime("%d/%m/%Y %H:%M")
                    sheet.update_cell(i, 8,  "✅ Lista")
                    sheet.update_cell(i, 9,  user)
                    sheet.update_cell(i, 11, now)
                    send_telegram(chat_id,
                        f"✅ Orden *{order_id}* de *{row.get('Cliente')}* marcada como lista.\n"
                        f"🛠️ Trabajo: {row.get('Trabajo')}"
                    )
                    broadcast(
                        f"✅ *{order_id}* lista\n"
                        f"👤 Cliente: {row.get('Cliente')}\n"
                        f"🛠️ Trabajo: {row.get('Trabajo')}\n"
                        f"👨‍🔧 Terminó: *{user}* — {now}",
                        exclude=chat_id
                    )
                    break
            if not found:
                send_telegram(chat_id, f"❌ No encontré una orden pendiente para *{nombre}*.")
        except Exception as e:
            send_telegram(chat_id, f"⚠️ Error: {e}")

    # ── /ordenes ────────────────────────────────────────────────────────────
    elif text == "/ordenes":
        try:
            sheet   = get_sheet()
            records = sheet.get_all_records()
            pendientes = [r for r in records if "Pendiente" in r.get("Estado", "")]
            if not pendientes:
                send_telegram(chat_id, "✅ No hay órdenes pendientes.")
            else:
                msg = f"📋 *Órdenes pendientes ({len(pendientes)}):*\n━━━━━━━━━━━━━━━━━\n"
                for r in pendientes[-10:]:
                    prio = {"Alta": "🔴", "Normal": "🟡", "Baja": "🟢"}.get(r.get("Prioridad", ""), "🟡")
                    msg += f"{prio} `{r['ID']}` — {r['Cliente']} — _{r.get('Trabajo','')[:35]}_\n"
                send_telegram(chat_id, msg)
        except Exception as e:
            send_telegram(chat_id, f"⚠️ Error: {e}")

    # ── /resumen (solo Martin) ───────────────────────────────────────────────
    elif text == "/resumen":
        if not is_admin:
            send_telegram(chat_id, "❌ Solo Martin puede usar este comando.")
        else:
            try:
                sheet   = get_sheet()
                records = sheet.get_all_records()
                total      = len(records)
                pendientes = len([r for r in records if "Pendiente" in r.get("Estado", "")])
                listas     = len([r for r in records if "Lista" in r.get("Estado", "")])
                alta       = len([r for r in records if r.get("Prioridad") == "Alta" and "Pendiente" in r.get("Estado", "")])
                msg = (
                    f"📊 *Resumen MZ GAMING*\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"📋 Total órdenes: *{total}*\n"
                    f"🟡 Pendientes: *{pendientes}*\n"
                    f"✅ Listas: *{listas}*\n"
                    f"🔴 Alta prioridad pendiente: *{alta}*\n"
                )
                send_telegram(chat_id, msg)
            except Exception as e:
                send_telegram(chat_id, f"⚠️ Error: {e}")

    # ── /cancelar ORD-XXX (solo Martin) ─────────────────────────────────────
    elif text.startswith("/cancelar "):
        if not is_admin:
            send_telegram(chat_id, "❌ Solo Martin puede cancelar órdenes.")
        else:
            order_id = text.split(" ", 1)[1].strip().upper()
            try:
                sheet   = get_sheet()
                records = sheet.get_all_records()
                for i, row in enumerate(records, start=2):
                    if row.get("ID", "").upper() == order_id:
                        sheet.update_cell(i, 8, "❌ Cancelada")
                        send_telegram(chat_id, f"🗑️ Orden *{order_id}* cancelada.")
                        broadcast(f"❌ Orden *{order_id}* cancelada por Martin.", exclude=chat_id)
                        break
            except Exception as e:
                send_telegram(chat_id, f"⚠️ Error: {e}")

    # ── /ayuda, /help, /start ────────────────────────────────────────────────
    elif text in ("/ayuda", "/help", "/start"):
        base_cmds = (
            f"👋 Hola *{user}*\n\n"
            f"🔧 *MZ GAMING — Servicio Técnico*\n\n"
            f"📋 *Comandos disponibles:*\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"`/ordenes` — Ver todas las órdenes pendientes\n"
            f"`/lista Nombre Cliente` — Marcar la orden de un cliente como lista\n"
            f"`/ayuda` — Mostrar esta ayuda\n"
        )
        if is_admin:
            base_cmds += (
                f"\n👑 *Comandos de admin:*\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"`/resumen` — Ver estadísticas generales\n"
                f"`/cancelar ORD\\-001` — Cancelar una orden por ID\n"
            )
        send_telegram(chat_id, base_cmds)

    return jsonify({"ok": True})

# ─── BUSINESS SHEETS ───────────────────────────────────────────────────────────
_BIZ_ALLOWED = {"Ventas", "Stock", "Clientes", "Bancos", "Gastos", "Productos", "Compras", "Resumen"}

@app.route("/api/biz/<sheet_name>")
def get_biz_sheet(sheet_name):
    if sheet_name not in _BIZ_ALLOWED:
        return jsonify({"ok": False, "error": "Hoja no permitida"}), 403
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet(sheet_name)
        rows = ws.get_all_values()
        if not rows:
            return jsonify({"ok": True, "data": []})
        headers = rows[0]
        # limpiar headers duplicados o vacíos
        seen = {}
        clean_headers = []
        for h in headers:
            h = h.strip()
            if not h:
                h = "_empty"
            if h in seen:
                seen[h] += 1
                h = f"{h}_{seen[h]}"
            else:
                seen[h] = 0
            clean_headers.append(h)
        records = []
        for row in rows[1:]:
            if any(cell.strip() for cell in row):
                records.append(dict(zip(clean_headers, row)))
        return jsonify({"ok": True, "data": records})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── SETUP ─────────────────────────────────────────────────────────────────────
@app.route("/setup-webhook")
def setup():
    base_url = request.host_url.rstrip("/")
    set_webhook(base_url)
    return "Webhook configurado ✓"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
