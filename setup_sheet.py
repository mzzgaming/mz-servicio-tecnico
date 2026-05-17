"""
Ejecutar UNA VEZ para crear los encabezados en Google Sheets.
python setup_sheet.py
"""
import os, json
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ.get("SHEET_ID", "")
SCOPES   = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
creds      = Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
client     = gspread.authorize(creds)
sheet      = client.open_by_key(SHEET_ID).sheet1

headers = ["ID", "Cliente", "Componentes", "Trabajo", "Fecha Entrega",
           "Prioridad", "Notas", "Estado", "Técnico", "Fecha Creación", "Fecha Cierre"]

sheet.clear()
sheet.append_row(headers)
sheet.format("A1:K1", {
    "textFormat": {"bold": True},
    "backgroundColor": {"red": 0.07, "green": 0.08, "blue": 0.12}
})
sheet.freeze(rows=1)

print("✅ Hoja configurada con encabezados.")
print(f"Columnas: {headers}")
