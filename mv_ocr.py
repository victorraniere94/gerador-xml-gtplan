"""OCR do relatório MV, com leitura posicional da coluna de quantidade solicitada."""
import io
import re
import fitz
import numpy as np
import pandas as pd
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ocr_engine = RapidOCR()
QUANT = re.compile(r"^\d{1,7}(?:[.,]\d{1,3})?$")
CODE = re.compile(r"^\d{1,7}$")


def _tokens(img):
    result, _ = ocr_engine(np.asarray(img))
    tokens = []
    for polygon, value, confidence in result or []:
        if confidence < 0.30:
            continue
        x = min(float(p[0]) for p in polygon)
        y = min(float(p[1]) for p in polygon)
        tokens.append((x, y, str(value).strip()))
    return tokens


def _horizontal(page):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    return img.rotate(270, expand=True)


def _parse(tokens, width):
    # Referência: relatório MV enviado, em orientação horizontal.
    # x relativo: sequência ~1%, código ~3%, produto 7-25%, quantidade solicitada ~38%.
    # Última compra fica ~63% e nunca é consultada.
    codes = []
    for x, y, value in tokens:
        if not (width * 0.025 <= x <= width * 0.065):
            continue
        match = CODE.fullmatch(value)
        if not match:
            # Alguns OCRs agrupam os dois números da coluna Seq.
            both = re.search(r"\b\d{1,3}\s+(\d{1,7})\b", value)
            if not both:
                continue
            value = both.group(1)
        # Só aceitar código se houver número de sequência na mesma linha à esquerda.
        sequence = any(
            xx < width * 0.027 and abs(yy - y) <= 14
            and re.fullmatch(r"\d{1,3}", tt)
            for xx, yy, tt in tokens
        )
        if sequence:
            codes.append((y, value))
    codes.sort()
    result = []
    for idx, (y, code) in enumerate(codes):
        next_y = codes[idx + 1][0] if idx + 1 < len(codes) else float("inf")
        qty_candidates = [
            (abs(yy-y), xx, t)
            for xx, yy, t in tokens
            if width * 0.365 <= xx <= width * 0.425
            and abs(yy - y) <= 20 and QUANT.fullmatch(t)
        ]
        qty_candidates.sort()
        # Não adivinhar quantidade quando OCR não reconhece a célula.
        if not qty_candidates:
            continue
        qty = qty_candidates[0][2]
        desc_tokens = [
            (yy, xx, t) for xx, yy, t in tokens
            if width * 0.065 <= xx <= width * 0.25
            and y - 12 <= yy < min(y + 65, next_y - 12)
            and not re.search(r"Rateio|Siaf|Siagem|Siafem|C[oó]d\.", t, re.I)
        ]
        desc_tokens.sort(key=lambda item: (round(item[0]/13), item[1]))
        desc = " ".join(t for _, _, t in desc_tokens).strip()
        if desc:
            result.append({"Código": code, "Descrição": desc, "Quantidade": qty})
    return result


def extract_mv(data):
    document = fitz.open(stream=data, filetype="pdf")
    if document.page_count > 15:
        raise ValueError("Limite de 15 páginas para PDFs.")
    rows = []
    for page in document:
        image = _horizontal(page)
        tokens = _tokens(image)
        rows.extend(_parse(tokens, image.width))
    return pd.DataFrame(rows, columns=["Código", "Descrição", "Quantidade"])
