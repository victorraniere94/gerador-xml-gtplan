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
    if pdf.page_count > 100:
        raise ValueError("O limite de segurança é de 100 páginas por PDF. Divida o arquivo em partes menores.")
    rows = []
    detected_sequences = []
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
        # Uma linha de produto é identificada pela quantidade solicitada,
        # não pelo valor numérico da coluna Seq. (que pode se repetir).
        # A linha de rateio também tem quantidade, mas não tem descrição/código.
        candidates = []
        for x, y, word in tokens:
            if not (.365 < x < .43 and NUMERO.fullmatch(word)):
                continue
            if any(xx < .02 and abs(yy-y) < 13 and "rateio" in w.lower() for xx, yy, w in tokens):
                continue
            if not any(.07 < xx < .265 and abs(yy-y) < 13
                       and re.search(r"[A-Za-zÀ-ÿ]", w)
                       for xx, yy, w in tokens):
                continue
            if any(abs(y-yy) < 12 for yy in candidates):
                continue
            candidates.append(y)
        candidates.sort()
        codes = []
        for y in candidates:
            code_tokens = [(abs(yy-y), w) for xx, yy, w in tokens
                           if .026 < xx < .07 and abs(yy-y) < 15
                           and re.fullmatch(r"\\d{1,7}", w)]
            code_tokens.sort()
            code = code_tokens[0][1] if code_tokens else ""
            # Código pode estar colado ao Seq. (ex.: 7/9721).
            if not code:
                fused = [(abs(yy-y), m.group(1))
                         for xx, yy, w in tokens if xx < .07 and abs(yy-y) < 15
                         for m in [re.search(r"[/|]([0-9]{2,7})$", w)]
                         if m]
                if fused:
                    code = min(fused)[1]
            if not code or len(code) <= 2:
                strip = image.crop((int(width*.006), max(0, int(y-12)),
                                    int(width*.072), min(image.height, int(y+17))))
                raw_strip = pytesseract.image_to_string(
                    strip.resize((strip.width*2, strip.height*2)),
                    lang="por", config="--psm 6"
                )
                nums = re.findall(r"\d+", raw_strip)
                seq_raw = sorted((abs(yy-y), w) for xx, yy, w in tokens
                                 if xx < .026 and abs(yy-y) < 15
                                 and re.fullmatch(r"\d{1,3}", w))
                seq_text = seq_raw[0][1] if seq_raw else ""
                for n in nums:
                    if seq_text and n.startswith(seq_text) and len(n) > len(seq_text):
                        suffix = n[len(seq_text):]
                        if len(suffix) > len(code):
                            code = suffix
                    elif not code and len(n) >= 2 and n != seq_text:
                        code = n
            if not code:
                # Releitura apenas da célula do código em alta resolução.
                crop = image.crop((int(width*.026), max(0, int(y-12)),
                                   int(width*.071), min(image.height, int(y+30))))
                reread = pytesseract.image_to_string(
                    crop.resize((crop.width*2, crop.height*2)),
                    lang="por", config="--psm 6"
                )
                found = re.search(r"\\d{2,7}", reread)
                if found:
                    code = found.group()
            if not code:
                continue
            seq_candidates = [(abs(yy-y), int(w)) for xx, yy, w in tokens
                              if xx < .026 and abs(yy-y) < 15
                              and re.fullmatch(r"\\d{1,3}", w)]
            if seq_candidates:
                detected_sequences.append((page_number, min(seq_candidates)[1]))
            codes.append((y, code))
        for idx, (y, code) in enumerate(codes):
            next_y = codes[idx+1][0] if idx+1 < len(codes) else float("inf")
            quantities = [(abs(yy-y), word) for x, yy, word in tokens
                          if .365 < x < .43 and abs(yy-y) < 16
                          and NUMERO.fullmatch(word)]
            quantities.sort()
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
    result = pd.DataFrame(rows, columns=["Código", "Descrição", "Quantidade"])
    result.attrs["mv_sequences"] = detected_sequences
    result.attrs["mv_product_rows"] = len(rows)
    return result
