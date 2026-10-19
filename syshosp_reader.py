"""Leitor Syshosp: Nº ignorado, Código + Descrição, unidade ignorada, Qtde."""
import io
import re
import fitz
import pandas as pd
import pytesseract
from PIL import Image

UNIT = r"(?:UND|UNID|UNIDADE|CX|CAIXA|PCT|PACOTE|FR|FRS|FRASCO|KG|ROLO|PAR|KIT|L|ML|BOBI|PECA|PEÇA)"
# A descrição termina no marcador de unidade, e a quantidade vem imediatamente depois.
ITEM = re.compile(
    rf"^\s*(\d{{1,4}})\s+(\d{{1,12}})\s*(.*?)\s*\(?{UNIT}\)?\s+(\d+(?:[.,]\d+)?)\s+(?:\d+|[^\s]+)",
    re.IGNORECASE,
)

def _read_lines(text):
    found = []
    for line in text.splitlines():
        m = ITEM.match(line)
        if not m:
            continue
        sequence, code, description, quantity = m.groups()
        if description.strip():
            found.append({"Código": code, "Descrição": description.strip(), "Quantidade": quantity})
    return found

def extract_syshosp(raw):
    doc = fitz.open(stream=raw, filetype="pdf")
    if doc.page_count > 15:
        raise ValueError("Limite de 15 páginas por PDF.")
    rows = []
    for page in doc:
        rows_page = _read_lines(page.get_text("text", sort=True))
        if not rows_page:
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            rows_page = _read_lines(pytesseract.image_to_string(image, lang="por", config="--psm 6"))
        rows.extend(rows_page)
    return pd.DataFrame(rows, columns=["Código", "Descrição", "Quantidade"])
