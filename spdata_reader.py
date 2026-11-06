"""Leitor de requisições SPData (texto PDF, com fallback OCR).
Colunas: Seq. (ignorar), Cod., Produto, UND (ignorar), Qtde.
"""
import io
import re
import fitz
import pandas as pd
from PIL import Image
import pytesseract

ROW = re.compile(
    r"^\s*(\d{1,4})\s+(\d{1,12})\s+(.+)\s+"
    r"(UNID|UND|UNIDADE|CX|CAIXA|PCT|PACOTE|FR|FRASCO|FRS|KG|L|ML|PAR|KIT|PC|PECA|PEÇA|BOBI|BOBINA|ROLO)\s+"
    r"(\d+(?:[.,]\d+)?)\s*(?:$|\s)",
    re.IGNORECASE,
)

def _parse(text):
    items = []
    for line in text.splitlines():
        # Layout SPData de necessidade de compra: colunas separadas por |.
        # Quantidade é a coluna 9 (índice 8), não estoque, consumo ou aprovada.
        if line.lstrip().startswith("|"):
            cols = [part.strip() for part in line.strip().strip("|").split("|")]
            if (len(cols) >= 9 and re.fullmatch(r"\d{1,12}", cols[0])
                    and cols[1] and re.fullmatch(r"\d+(?:\.\d{3})*,\d+|\d+(?:[.,]\d+)?", cols[8])):
                description = re.sub(r"\.{2,}\s*$", "", cols[1]).strip()
                if description:
                    items.append({"Código": cols[0], "Descrição": description,
                                  "Quantidade": cols[8]})
                continue
        # Layout SPData anterior: Seq, Código, Descrição, UND, Quantidade.
        m = ROW.match(line)
        if m:
            seq, code, description, unit, quantity = m.groups()
            items.append({"Código": code, "Descrição": description.strip(), "Quantidade": quantity})
    return items

def extract_spdata(raw):
    doc = fitz.open(stream=raw, filetype="pdf")
    if doc.page_count > 15:
        raise ValueError("Limite de 15 páginas por PDF.")
    items = []
    for page in doc:
        text = page.get_text("text", sort=True)
        parsed = _parse(text)
        if not parsed:
            pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            parsed = _parse(pytesseract.image_to_string(img, lang="por", config="--psm 6"))
        items.extend(parsed)
    return pd.DataFrame(items, columns=["Código", "Descrição", "Quantidade"])
