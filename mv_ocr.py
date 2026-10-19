"""Leitura experimental de solicitações MV digitalizadas.
A coluna Quantidade em Dados da Solicitação é a única fonte de quantidade.
"""
import io
import re
import numpy as np
import pandas as pd
import fitz
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

OCR = RapidOCR()
UNITS = r"(?:UNIDADE|UND|UN|FRASCO|CAIXA|PACOTE|PECA|PEÇA|KIT|ROLO|PAR|LITRO|METRO|AMPOLA|BOLSA|COMPRIMIDO)"
NUMBER = r"\d+(?:[.,]\d{1,3})?"
ROW = re.compile(
    rf"^\s*(\d{{3,}})\s+(.+?)\s+(?:[A-Z])\s+({UNITS})\s+({NUMBER})(?=\s|$)",
    re.I
)

def _lines(image):
    results, _ = OCR(np.array(image))
    if not results:
        return []
    return [(float(min(p[1] for p in polygon)), float(min(p[0] for p in polygon)), str(text).strip())
            for polygon, text, score in results if score >= 0.35 and str(text).strip()]

def _recognize(page):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    candidates = []
    for angle in (0, 90, 270, 180):
        rotated = img.rotate(angle, expand=True)
        lines = _lines(rotated)
        joined = " ".join(x[2].upper() for x in lines)
        score = sum(word in joined for word in ("SOLICITA", "QUANTIDADE", "PRODUTO", "SEQ", "UNIDADE"))
        score += sum(bool(re.search(r"\b\d{3,}\b", x[2])) for x in lines)
        candidates.append((score, lines))
    return max(candidates, key=lambda x: x[0])[1]

def _parse_layout(lines, width):
    """Lê códigos e quantidades pela posição das colunas, nunca pela última compra."""
    # Os recortes são proporcionais à largura da página já colocada na horizontal.
    # Seq e código: 0-7%; produto: 7-25%; quantidade solicitada: 36-43%.
    tokens = [(y, x, t) for y, x, t in lines]
    candidates = []
    for y, x, txt in tokens:
        if x >= width * 0.075:
            continue
        nearby = sorted(
            [(xx, tt) for yy, xx, tt in tokens
             if abs(yy - y) <= 13 and xx < width * 0.078],
            key=lambda z: z[0]
        )
        left = " ".join(t for _, t in nearby)
        match = re.search(r"(?<!\\d)(\\d{1,3})\\s+(\\d{1,7})(?!\\d)", left)
        if not match:
            continue
        seq, code = match.groups()
        if not any(abs(y - existing[0]) < 15 for existing in candidates):
            candidates.append((y, code))
    candidates.sort()
    items = []
    for idx, (y, code) in enumerate(candidates):
        next_y = candidates[idx + 1][0] if idx + 1 < len(candidates) else float("inf")
        row_tokens = [(yy, xx, tt) for yy, xx, tt in tokens if abs(yy - y) <= 15]
        qty_tokens = [(xx, tt) for _, xx, tt in row_tokens
                      if width * 0.365 <= xx <= width * 0.43]
        qty_tokens.sort()
        qty = next((m.group() for _, t in qty_tokens
                    if (m := re.search(r"\\d+(?:[.,]\\d{1,3})?", t))), None)
        description_parts = [
            (yy, xx, tt) for yy, xx, tt in tokens
            if y - 8 <= yy < min(y + 55, next_y - 10)
            and width * 0.07 <= xx < width * 0.25
            and not re.search(r"Rateio|C[oó]d\\.|Siaf|Siagem|Siafem", tt, re.I)
        ]
        description_parts.sort(key=lambda z: (round(z[0] / 12), z[1]))
        desc = " ".join(t for _, _, t in description_parts).strip()
        if code and desc and qty:
            items.append({"Código": code, "Descrição": desc, "Quantidade": qty})
    return items


def extract_mv(data):
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.page_count > 15:
        raise ValueError("Limite de 15 páginas para PDFs.")
    rows = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        # Relatórios MV deste modelo chegam girados; a orientação correta é horizontal.
        rotated = img.rotate(270, expand=True)
        lines = _lines(rotated)
        rows.extend(_parse_layout(lines, rotated.width))
    return pd.DataFrame(rows, columns=["Código", "Descrição", "Quantidade"])
