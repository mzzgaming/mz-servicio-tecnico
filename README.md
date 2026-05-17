# MZ GAMING — Sistema de Servicio Técnico

Panel web + Bot Telegram para gestión de órdenes de trabajo. v1.1

---

## 🏗️ Estructura

```
mz-servicio-tecnico/
├── app.py              ← Backend Flask (API + webhook Telegram)
├── setup_sheet.py      ← Configura Google Sheets (ejecutar 1 vez)
├── requirements.txt
├── Procfile            ← Para Railway
└── templates/
    ├── index.html      ← Formulario nueva orden
    └── orders.html     ← Dashboard de órdenes
```

---

## ⚙️ Variables de entorno (Railway)

| Variable | Descripción |
|---|---|
| `SHEET_ID` | ID de tu Google Sheet |
| `BOT_TOKEN` | Token del BOT NUEVO de técnicos |
| `TECHNICIANS_CHAT_ID` | ID del grupo de Telegram de técnicos |
| `GOOGLE_CREDENTIALS_JSON` | JSON completo de la service account |
| `WEBHOOK_SECRET` | Secreto para el webhook (cualquier string) |
| `PORT` | Railway lo setea automáticamente |

---

## 🚀 Pasos de instalación

### 1. Crear el bot de Telegram
1. Abrí @BotFather en Telegram
2. `/newbot` → poné nombre: `MZ GAMING Técnicos`
3. Guardá el token → va a `BOT_TOKEN`

### 2. Crear el grupo de técnicos
1. Creá un grupo en Telegram con tus técnicos
2. Agregá el bot al grupo como administrador
3. Mandá un mensaje en el grupo
4. Entrá a: `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. El `chat.id` del grupo es negativo, ej: `-1001234567890` → va a `TECHNICIANS_CHAT_ID`

### 3. Google Sheets
1. Creá una hoja nueva en Google Drive
2. Copiá el ID de la URL (entre /d/ y /edit)
3. Compartí la hoja con el email de tu service account (el mismo que usás en el bot de gastos)

### 4. Subir a Railway
```bash
# En la carpeta del proyecto:
git init
git add .
git commit -m "MZ Gaming servicio técnico"
# Crear nuevo proyecto en Railway y conectar repo
```

5. Configurar todas las variables de entorno en Railway

### 5. Configurar la hoja (1 vez)
```bash
# Con las variables de entorno seteadas localmente:
python setup_sheet.py
```

### 6. Activar el webhook
Una vez deployado, entrá a:
```
https://tu-app.railway.app/setup-webhook
```

---

## 💬 Comandos del bot para técnicos

| Comando | Acción |
|---|---|
| `/ordenes` | Ver todas las órdenes pendientes |
| `/lista ORD-001` | Marcar la orden ORD-001 como lista |
| `/help` | Ver ayuda |

---

## 🖥️ Panel web

| URL | Descripción |
|---|---|
| `/` | Formulario nueva orden |
| `/orders` | Dashboard de órdenes |
| `/api/orders` | API REST (GET/POST) |
