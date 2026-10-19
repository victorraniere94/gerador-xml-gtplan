"""OCR local do relatório MV (formato com colunas Seq, Produto e Dados da Solicitação).
A leitura é preliminar: todos os itens devem ser conferidos com o PDF.
"""
import io
import re
import fitz
import pandas as pd
import pytesseract
from PIL import Image

NUMERO = re.compile(r"\d{1,3}(?:\.\d{3})*,\d+|\d+(?:[.,]\d+)?")

def extract_mv(data):
    pdf = fitz.open(stream=data, filetype="pdf")
    if pdf.page_count > 15:
        raise ValueError("O limite é de 15 páginas por PDF.")
    rows = []
    for page_number, page in enumerate(pdf, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
        image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        # A diagramação MV enviada tem páginas giradas 90 graus.
        if image.height > image.width:
            image = image.rotate(270, expand=True)
        width = image.width
        data_ocr = pytesseract.image_to_data(
            image, lang="por", config="--psm 6",
            output_type=pytesseract.Output.DICT
        )
        tokens = [
            (data_ocr["left"][i] / width, data_ocr["top"][i], word.strip())
            for i, word in enumerate(data_ocr["text"]) if word.strip()
        ]
        # Exige sequência à esquerda do código para evitar cabeçalhos e rateios.
        codes = []
        for x, y, word in tokens:
            if not (.026 < x < .055 and re.fullmatch(r"\d{1,7}", word)):
                continue
            if any(
                xx < .026 and abs(yy-y) < 15 and re.fullmatch(r"\d{1,3}", w)
                for xx, yy, w in tokens
            ):
                codes.append((y, word))
        codes.sort()
        for idx, (y, code) in enumerate(codes):
            next_y = codes[idx+1][0] if idx+1 < len(codes) else float("inf")
            quantities = [
                (abs(yy-y), word)
                for x, yy, word in tokens
                if .365 < x < .43 and abs(yy-y) < 16
                and NUMERO.fullmatch(word)
            ]
            quantities.sort()
            # Não usar números de outras colunas como alternativa.
            if not quantities:
                continue
            # Agrupar palavras da descrição respeitando a posição horizontal.
            words = [
                (yy, x, word)
                for x, yy, word in tokens
                if .07 < x < .265 and y-12 <= yy < min(y+75, next_y-12)
                and not re.search(r"Rateio|Siaf|Siagem|Siafem|C[oó]d\.", word, re.I)
            ]
            words.sort(key=lambda item: (round(item[0]/16), item[1]))
            description = " ".join(word for _, _, word in words).strip()
            if description:
                rows.append({
                    "Código": code, "Descrição": description,
                    "Quantidade": quantities[0][1]
                })
    return pd.DataFrame(rows, columns=["Código", "Descrição", "Quantidade"])
