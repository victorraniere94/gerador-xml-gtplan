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

def extract_mv(data):
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.page_count > 15:
        raise ValueError("Limite de 15 páginas para PDFs.")
    rows = []
    for page in doc:
        lines = _recognize(page)
        if not lines:
            continue
        # Agrupa trechos próximos na mesma linha, da esquerda para a direita.
        lines.sort(key=lambda x: (round(x[0] / 16), x[1]))
        groups = []
        for y, x, txt in lines:
            target = next((g for g in groups if abs(g[0] - y) < 13), None)
            if target is None:
                target = [y, []]
                groups.append(target)
            target[1].append((x, txt))
        for _, fragments in groups:
            row = " ".join(text for _, text in sorted(fragments))
            match = ROW.search(row)
            if match:
                code, desc, unit, qty = match.groups()
                rows.append({"Código": code, "Descrição": desc.strip(), "Quantidade": qty})
    if not rows:
        raise ValueError(
            "Não foi possível reconhecer com segurança os itens na tabela MV. "
            "O PDF pode ter qualidade ou diagramação diferente; não geramos quantidades por estimativa. "
            "Envie uma planilha Excel/CSV ou solicite ajuste do leitor para este documento."
        )
    return pd.DataFrame(rows)
