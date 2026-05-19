import os
import json
import base64
import io
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, make_response
import gspread
from google.oauth2.service_account import Credentials
import requests

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))

# ─── USUARIOS ─────────────────────────────────────────────────────────────────
ADMIN_IDS = {909301871, 8832743374}  # Martin y MZ Gaming (admins)

TECHNICIANS = {
    909301871: "Martin",
    8832743374: "Mz Gaming",
    5521238474: "Alvaro",
    7837832832: "Adrian",
}

ALL_CHAT_IDS = list(TECHNICIANS.keys())

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SHEET_ID          = os.environ.get("SHEET_ID", "")
BUSINESS_SHEET_ID = os.environ.get("BUSINESS_SHEET_ID", "1FHEBuzVEkpg_w8dDMP_Y1YeZBtUprtG9")
BOT_TOKEN         = os.environ.get("BOT_TOKEN", "")
WEBHOOK_SECRET    = os.environ.get("WEBHOOK_SECRET", "mzgaming2024")

SECRET_KEY = os.environ.get("SECRET_KEY", "mzgaming_secret_2024")
app.secret_key = SECRET_KEY

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("username", "")
        pwd = request.form.get("password", "")
        if user == os.environ.get("DASHBOARD_USER", "mzgaming") and pwd == os.environ.get("DASHBOARD_PASSWORD", "7799"):
            session['logged_in'] = True
            return redirect(url_for('orders_page'))
        else:
            error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

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
@requires_auth
def index():
    return render_template("index.html")

@app.route("/orders")
@requires_auth
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

HEADER_ROWS = {
    "Ventas": 4,
    "Compras": 2,
    "Gastos": 2,
    "Productos": 6,
    "Clientes": 3,
    "Bancos": 6,
    "Stock": 2,
    "Resumen": 1,
}

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
        all_values = ws.get_all_values()
        header_row = HEADER_ROWS.get(sheet_name, 1) - 1
        if not all_values or len(all_values) <= header_row:
            return jsonify({"ok": True, "data": []})
        headers = all_values[header_row]
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
        for row in all_values[header_row + 1:]:
            if any(cell.strip() for cell in row):
                records.append(dict(zip(clean_headers, row)))
        records = [r for r in records if any(str(v).strip() and str(v).strip() != '0' for k,v in r.items() if not k.startswith('_empty'))]
        return jsonify({"ok": True, "data": records})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── BUSINESS SHEETS — ESCRITURA ───────────────────────────────────────────────
@app.route("/api/biz/Ventas", methods=["POST"])
def add_venta():
    try:
        data = request.json
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet("Ventas")
        row = [
            data.get("fecha", ""),
            data.get("cliente", ""),
            data.get("descripcion", ""),
            data.get("importe", ""),
            data.get("estado", "Pendiente"),
            data.get("medio_pago", ""),
            data.get("tipo_servicio", ""),
            data.get("producto", ""),
            data.get("cantidad", ""),
            "",
            data.get("abonado", ""),
            "",
            data.get("facturado", "No"),
            data.get("tipo_factura", ""),
            ""
        ]
        ws.append_row(row)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/biz/Compras", methods=["POST"])
def add_compra():
    try:
        data = request.json
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet("Compras")
        row = [
            data.get("fecha", ""),
            data.get("descripcion", ""),
            data.get("proveedor", ""),
            data.get("importe_usd", ""),
            data.get("estado", "Pendiente"),
            data.get("notas", ""),
            data.get("medio_pago", ""),
            data.get("producto", ""),
            data.get("cantidad", ""),
            "",
            data.get("importe_ars", "")
        ]
        ws.append_row(row)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/biz/Gastos", methods=["POST"])
def add_gasto():
    try:
        data = request.json
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet("Gastos")
        row = [
            data.get("fecha", ""),
            data.get("categoria", ""),
            data.get("importe", ""),
            data.get("descripcion", ""),
            data.get("medio_pago", ""),
            data.get("responsable", "")
        ]
        ws.append_row(row)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/biz/Clientes", methods=["POST"])
def add_cliente():
    try:
        data = request.json
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet("Clientes")
        row = [
            data.get("cliente", ""),
            data.get("telefono", ""),
            data.get("tipo_cliente", ""),
            data.get("abono", ""),
            data.get("plan", ""),
            data.get("estado", "Activo"),
            "",
            "",
            data.get("notas", "")
        ]
        ws.append_row(row)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/biz/Productos", methods=["POST"])
def add_producto():
    try:
        data = request.json
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet("Productos")
        row = [
            data.get("codigo", ""),
            data.get("nombre", ""),
            data.get("categoria", ""),
            data.get("marca", ""),
            data.get("stock_actual", ""),
            data.get("stock_minimo", ""),
            data.get("precio_compra_usd", ""),
            data.get("precio_venta_usd", ""),
            "",
            data.get("stock_actual", ""),
            "",
            ""
        ]
        ws.append_row(row)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── DEBUG (temporal) ──────────────────────────────────────────────────────────
@app.route("/api/biz/<sheet_name>/raw")
def get_biz_raw(sheet_name):
    if sheet_name not in _BIZ_ALLOWED:
        return jsonify({"ok": False, "error": "Hoja no permitida"}), 403
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet(sheet_name)
        rows = ws.get_all_values()
        return jsonify({"ok": True, "rows": [{"row": i+1, "data": r} for i, r in enumerate(rows[:20])]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ─── BUSCAR CLIENTE ────────────────────────────────────────────────────────────
@app.route("/api/buscar-cliente")
@requires_auth
def buscar_cliente():
    q = request.args.get("q", "").strip().replace("-", "").replace(" ", "")
    if not q:
        return jsonify({"ok": False})

    # 1. Buscar en sheet propio
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet("Clientes")
        rows = ws.get_all_values()
        if len(rows) >= 3:
            headers = rows[2]  # HEADER_ROWS["Clientes"] = 3
            for row in rows[3:]:
                if not any(row):
                    continue
                record = dict(zip(headers, row))
                nombre = record.get("Cliente", "")
                telefono = record.get("Teléfono", "").replace("-", "").replace(" ", "")
                if q in telefono or q.lower() in nombre.lower():
                    return jsonify({"ok": True, "fuente": "sheet", "cliente": {
                        "nombre": nombre,
                        "tipo": record.get("Tipo cliente", "Consumidor Final"),
                        "domicilio": "",
                        "condicion_iva": record.get("Tipo cliente", "Consumidor Final"),
                    }})
    except Exception:
        pass

    # 2. Consultar TangoFactura (solo si q parece un CUIT)
    if q.isdigit() and len(q) >= 10:
        try:
            r = requests.get(
                f"https://afip.tangofactura.com/Rest/GetContribuyenteFull?cuit={q}",
                timeout=5
            )
            data = r.json()
            if data and data.get("Contribuyente") and data["Contribuyente"].get("Nombre"):
                c = data["Contribuyente"]
                return jsonify({"ok": True, "fuente": "afip", "cliente": {
                    "nombre": c.get("Nombre", ""),
                    "tipo": c.get("CondicionIva", "Consumidor Final"),
                    "domicilio": c.get("Domicilio", ""),
                    "condicion_iva": c.get("CondicionIva", "Consumidor Final"),
                }})
        except Exception:
            pass

    return jsonify({"ok": False})

# ─── PRESUPUESTOS ──────────────────────────────────────────────────────────────
@app.route("/presupuestos")
@requires_auth
def presupuestos_page():
    return render_template("presupuestos.html")

@app.route("/api/presupuesto/numero", methods=["GET"])
@requires_auth
def get_numero_presupuesto():
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        try:
            ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet("Presupuestos")
            values = ws.get_all_values()
            numero = len(values)
        except:
            numero = 0
        return jsonify({"ok": True, "numero": numero + 1})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/presupuesto", methods=["POST"])
@requires_auth
def crear_presupuesto():
    try:
        data = request.json
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        try:
            ws = client.open_by_key(BUSINESS_SHEET_ID).worksheet("Presupuestos")
        except:
            sh = client.open_by_key(BUSINESS_SHEET_ID)
            ws = sh.add_worksheet(title="Presupuestos", rows=1000, cols=10)
            ws.append_row(["N°", "Fecha", "Cliente", "Tipo", "Total", "IVA", "Estado"])
        numero = data.get("numero", "")
        ws.append_row([
            numero,
            data.get("fecha", ""),
            data.get("cliente", ""),
            data.get("tipo", ""),
            data.get("total", ""),
            data.get("iva_total", ""),
            "Pendiente"
        ])
        return jsonify({"ok": True, "numero": numero})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/presupuesto/pdf", methods=["POST"])
@requires_auth
def generar_pdf():
    try:
        from weasyprint import HTML
        data = request.json
        html_content = generar_html_presupuesto(data)
        pdf = HTML(string=html_content).write_pdf()
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=presupuesto_{data.get("numero","")}.pdf'
        return response
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

def generar_html_presupuesto(data):
    cliente = data.get("cliente", "")
    tipo = data.get("tipo", "Presupuesto B")
    numero = str(data.get("numero", 1)).zfill(6)
    numero_display = f"00004 - {numero}"
    fecha = data.get("fecha", "")
    vencimiento = data.get("vencimiento", "")
    items = data.get("items", [])
    notas = data.get("notas", "")

    subtotal = sum(float(i.get("cantidad",0)) * float(i.get("precio",0)) * (1 - float(i.get("descuento",0))/100) for i in items)
    iva_pct = 21 if "A" in tipo else 0
    iva_monto = subtotal * iva_pct / 100
    total = subtotal + iva_monto

    items_html = ""
    for i, item in enumerate(items, 1):
        cant = float(item.get("cantidad", 0))
        precio = float(item.get("precio", 0))
        desc = float(item.get("descuento", 0))
        subtot = cant * precio * (1 - desc/100)
        items_html += f"""
        <tr>
            <td>{i}</td>
            <td>{item.get("descripcion","")}</td>
            <td style="text-align:center">{cant:.0f}</td>
            <td style="text-align:right">${precio:,.2f}</td>
            <td style="text-align:center">{desc:.0f}%</td>
            <td style="text-align:right">${subtot:,.2f}</td>
        </tr>"""

    logo_b64 = ""
    try:
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "MZ_Logo.png")
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
    except:
        pass
    logo_tag = f'<img src="data:image/png;base64,{logo_b64}" style="height:70px;">' if logo_b64 else ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 12px; color: #222; margin: 0; padding: 24px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #8b0000; padding-bottom: 16px; margin-bottom: 20px; }}
  .empresa h2 {{ color: #8b0000; font-size: 18px; margin: 0 0 4px; }}
  .empresa p {{ margin: 2px 0; color: #444; font-size: 11px; }}
  .doc-info {{ text-align: right; }}
  .doc-info h1 {{ font-size: 22px; color: #8b0000; margin: 0 0 6px; font-style: italic; font-weight: bold; }}
  .doc-info p {{ margin: 2px 0; font-size: 11px; color: #333; }}
  .doc-info .original {{ font-size: 10px; color: #666; }}
  .cliente-box {{ background: #f5f5f5; border-left: 4px solid #8b0000; padding: 12px 16px; margin-bottom: 20px; border-radius: 0 8px 8px 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  thead tr {{ background: #8b0000; color: white; }}
  thead th {{ padding: 10px 8px; text-align: left; font-size: 11px; }}
  tbody tr:nth-child(even) {{ background: #f9f9f9; }}
  tbody td {{ padding: 8px; border-bottom: 1px solid #eee; }}
  .totales {{ display: flex; justify-content: flex-end; }}
  .totales-box {{ width: 280px; }}
  .totales-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #eee; font-size: 12px; }}
  .totales-row.total {{ font-weight: bold; font-size: 15px; color: #8b0000; border-bottom: none; padding-top: 10px; }}
  .footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 12px; text-align: center; color: #888; font-size: 10px; }}
</style>
</head>
<body>
<div class="header">
  <div style="display:flex;align-items:center;gap:16px;">
    {logo_tag}
    <div class="empresa">
      <h2>MZ GAMING</h2>
      <p>Santiago Del Estero 80, Salta (4400), Argentina</p>
      <p>Tel: 387-2510080 | mzzgaming@hotmail.com</p>
      <p>CUIT: 20-39535176-2 | Responsable Inscripto</p>
      <p>Ingresos Brutos N°: 20395351762</p>
      <p>Inicio de actividad: 02-02-2021</p>
    </div>
  </div>
  <div class="doc-info">
    <h1>{tipo}</h1>
    <p class="original">Original</p>
    <p><strong>N° {numero_display}</strong></p>
    <p>Fecha: {fecha}</p>
    <p>C.U.I.T.: 20-39535176-2</p>
    <p>Ingresos brutos N° 20395351762</p>
    <p>Inicio de actividad 02-02-2021</p>
  </div>
</div>

<div class="cliente-box">
  <strong>Cliente:</strong> {cliente}<br>
  <small style="color:#666">Condición frente al IVA: Consumidor Final</small>
</div>

<table>
  <thead>
    <tr>
      <th>#</th><th>Descripción</th>
      <th style="text-align:center">Cant.</th>
      <th style="text-align:right">P. Unit.</th>
      <th style="text-align:center">Desc.</th>
      <th style="text-align:right">Subtotal</th>
    </tr>
  </thead>
  <tbody>{items_html}</tbody>
</table>

<div class="totales">
  <div class="totales-box">
    <div class="totales-row"><span>Subtotal:</span><span>${subtotal:,.2f}</span></div>
    {"<div class='totales-row'><span>IVA 21%:</span><span>$" + f"{iva_monto:,.2f}" + "</span></div>" if iva_pct > 0 else ""}
    <div class="totales-row total"><span>TOTAL:</span><span>${total:,.2f}</span></div>
  </div>
</div>

{"<div style='margin-top:20px;padding:12px;background:#f5f5f5;border-radius:8px;'><strong>Notas:</strong> " + notas + "</div>" if notas else ""}

<div class="footer">
  Este documento no tiene validez fiscal · MZ GAMING © 2026 · Santiago Del Estero 80, Salta, Argentina
</div>
</body>
</html>"""

# ─── SETUP ─────────────────────────────────────────────────────────────────────
@app.route("/setup-webhook")
def setup():
    base_url = request.host_url.rstrip("/")
    set_webhook(base_url)
    return "Webhook configurado ✓"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
