"""Extrai Código, Produto e Qtd. Solicitada de pedidos SMED.

Usa as posições das colunas e das linhas da tabela no PDF, inclusive quando
as descrições dos produtos ocupam várias linhas. Não usa Estoque nem Preço.
"""
import re
import unicodedata

import fitz
import pandas as pd

COLUMNS = ["Código", "Descrição", "Quantidade"]
CODE = re.compile(r"\d{1,12}")
QUANTITY = re.compile(r"\d+(?:\.\d{3})*(?:,\d+)?|\d+(?:\.\d+)?")


def _plain(value):
    return "".join(ch for ch in unicodedata.normalize("NFKD", value.lower())
                   if not unicodedata.combining(ch)).strip(" .:")


def _words(page):
    result = []
    rotation = page.rotation_matrix
    for x0, y0, x1, y1, value, *_ in page.get_text("words"):
        box = fitz.Rect(x0, y0, x1, y1) * rotation
        result.append({"text": value, "x0": box.x0, "x1": box.x1,
                       "y0": box.y0, "y1": box.y1,
                       "cx": (box.x0 + box.x1) / 2,
                       "cy": (box.y0 + box.y1) / 2})
    return result


def _horizontal_lines(page):
    result = []
    rotation = page.rotation_matrix
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] != "l":
                continue
            first, last = item[1:3]
            box = (fitz.Rect(min(first.x, last.x), min(first.y, last.y),
                             max(first.x, last.x), max(first.y, last.y)) * rotation)
            if box.height <= 1.5 and box.width >= 20:
                result.append((box.x0, box.x1, (box.y0 + box.y1) / 2))
    return result


def _find_header(words):
    for code in words:
        if _plain(code["text"]) not in ("cod", "codigo"):
            continue
        near = [w for w in words if abs(w["cy"] - code["cy"]) < 4]
        product = next((w for w in near if _plain(w["text"]) == "produto"), None)
        requested = next((w for w in near if _plain(w["text"]) == "solicitada"), None)
        if product and requested and code["cx"] < product["cx"] < requested["cx"]:
            return code, product, requested
    return None


def _column_for_header(lines, header, y):
    candidates = [(left, right) for left, right, line_y in lines
                  if abs(line_y - y) < 1.0 and left - 1 <= header["cx"] <= right + 1]
    if not candidates:
        return None
    return min(candidates, key=lambda col: col[1] - col[0])


def _layout(page, words):
    header = _find_header(words)
    if header is None:
        return None
    cod, product, requested = header
    lines = _horizontal_lines(page)
    heading_bottom = max(w["y1"] for w in header)
    # A linha inferior do cabeçalho cobre a largura da tabela.
    candidates = sorted({round(y, 1) for _, _, y in lines
                         if heading_bottom + 1 < y < heading_bottom + 22})
    for y in candidates:
        code_col = _column_for_header(lines, cod, y)
        product_col = _column_for_header(lines, product, y)
        quantity_col = _column_for_header(lines, requested, y)
        if code_col and product_col and quantity_col and code_col[1] <= product_col[0] + 1:
            boundaries = sorted(set(round(yy, 1) for x0, x1, yy in lines
                                    if yy >= y - 0.5 and
                                    abs(x0 - product_col[0]) <= 2 and
                                    abs(x1 - product_col[1]) <= 2))
            return code_col, product_col, quantity_col, boundaries

    # PDFs sem linhas vetoriais: estima as bandas pelos títulos, mantendo
    # o campo Quantidade longe de Estoque e Preço.
    next_heading = next((w for w in words
                         if _plain(w["text"]) == "preco" and
                         abs(w["cy"] - cod["cy"]) < 4), None)
    supplier_heading = next((w for w in words
                             if _plain(w["text"]) == "ultimo" and
                             abs(w["cy"] - cod["cy"]) < 4), None)
    if next_heading is None or supplier_heading is None:
        return None
    code_end = cod["x1"] + 4
    product_end = supplier_heading["x0"] - 35
    qty_start = requested["x0"] - 22
    qty_end = next_heading["x0"] - 4
    if product_end <= code_end or qty_end <= qty_start:
        return None
    return (cod["x0"] - 12, code_end), (code_end, product_end), (qty_start, qty_end), [heading_bottom + 4]


def _cell_words(words, col, top, bottom):
    return [w for w in words if col[0] - 1 <= w["cx"] <= col[1] + 1
            and top + 0.5 < w["cy"] < bottom - 0.5]


def _description(words):
    """Recompõe linhas de texto sem perder a ordem do produto."""
    chunks = []
    for word in sorted(words, key=lambda w: (w["cy"], w["x0"])):
        row = next((item for item in chunks if abs(item[0] - word["cy"]) < 2), None)
        if row is None:
            row = [word["cy"], []]
            chunks.append(row)
        row[1].append(word)
    chunks.sort(key=lambda chunk: chunk[0])
    return " ".join(" ".join(w["text"] for w in sorted(row, key=lambda w: w["x0"]))
                    for _, row in chunks).strip()


def _row(words, cols, top, bottom):
    code_words = _cell_words(words, cols[0], top, bottom)
    codes = [w["text"] for w in code_words if CODE.fullmatch(w["text"])]
    if not codes:
        return None
    # Uma linha deve ter um único código. No caso de dados incertos, a
    # conferência humana é mais segura que atribuir o item errado.
    if len(codes) != 1:
        return None
    description = _description(_cell_words(words, cols[1], top, bottom))
    quantities = [w["text"] for w in _cell_words(words, cols[2], top, bottom)
                  if QUANTITY.fullmatch(w["text"])]
    quantity = quantities[0] if len(quantities) == 1 else ""
    return {"Código": codes[0], "Descrição": description, "Quantidade": quantity}


def _extract_page(page):
    words = _words(page)
    layout = _layout(page, words)
    if layout is None:
        return []
    code_col, product_col, qty_col, borders = layout
    cols = (code_col, product_col, qty_col)
    rows = []
    if len(borders) > 1:
        for upper, lower in zip(borders[:-1], borders[1:]):
            row = _row(words, cols, upper, lower)
            if row is not None:
                rows.append(row)
        return rows
    # Sem divisórias, usa as posições dos códigos como âncoras. Cada grupo
    # vai até a metade da distância entre os códigos vizinhos.
    anchors = sorted(w["cy"] for w in words
                     if w["cy"] > borders[0] and
                     code_col[0] <= w["cx"] <= code_col[1] and
                     CODE.fullmatch(w["text"]))
    if not anchors:
        return []
    midpoints = [(a + b) / 2 for a, b in zip(anchors[:-1], anchors[1:])]
    spans = [borders[0]] + midpoints + [page.rect.height - 15]
    for upper, lower in zip(spans[:-1], spans[1:]):
        row = _row(words, cols, upper, lower)
        if row is not None:
            rows.append(row)
    return rows


def extract_smed(raw):
    doc = fitz.open(stream=raw, filetype="pdf")
    if doc.page_count > 15:
        raise ValueError("Limite de 15 páginas por PDF.")
    rows = []
    try:
        for page in doc:
            rows.extend(_extract_page(page))
    finally:
        doc.close()
    return pd.DataFrame(rows, columns=COLUMNS)
