import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Gerador XML GTPlan", page_icon="📄", layout="wide")
st.title("Gerador de XML — GTPlan")
st.caption("Layout WA • Arquivos processados nesta sessão • Não envie dados confidenciais até validação interna.")
st.info("Use apenas planilhas autorizadas. Este aplicativo pode ser acessado por qualquer pessoa com o endereço público.")

col_formato, col_erp = st.columns(2)
with col_formato:
    tipo_entrada = st.radio("Formato do arquivo de origem", ["Excel / CSV", "PDF (OCR)"], horizontal=True)
with col_erp:
    if tipo_entrada == "PDF (OCR)":
        erp = st.radio("ERP de origem", ["MV", "SPData", "Syshosp", "SMED"], horizontal=True)
    else:
        erp = None
        st.caption("ERP de origem: não se aplica a Excel / CSV")

if tipo_entrada == "PDF (OCR)":
    arquivo = st.file_uploader("Enviar PDF da requisição (até 10 MB)", type=["pdf"], key="pdf_upload")
    if erp != "MV":
        st.warning(f"A leitura automática do ERP {erp} ainda não foi configurada. Por enquanto, utilize o modelo MV ou Excel/CSV.")
else:
    arquivo = st.file_uploader("Importe Excel (.xlsx) ou CSV com código, descrição e quantidade (máximo 10 MB)", type=["xlsx", "csv"])
    st.caption("A quantidade deve ser a quantidade final solicitada, sem multiplicação por embalagem. Códigos e descrições são mantidos como texto.")

complemento = st.text_input("Complemento opcional do código dos produtos", placeholder="Ex.: POLICLINICA", help="Será acrescentado ao final de cada Codigo_Produto no XML.")
hora = st.text_input("Hora de vencimento", value="15:41")
titulo = st.text_input("Título da PDC (opcional)")
observacao = st.text_area("Observação (opcional)", height=75)
campo_extra_nome = st.text_input("Nome do campo extra", value="Não Programada")
campo_extra_valor = st.text_input("Valor do campo extra (opcional)")

def load_table(upload):
    raw = upload.getvalue()
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("O arquivo ultrapassa 10 MB.")
    if upload.name.lower().endswith(".pdf"):
        from mv_ocr import extract_mv
        return extract_mv(raw)
    if upload.name.lower().endswith(".xlsx"):
        sheet = st.selectbox("Aba da planilha", pd.ExcelFile(io.BytesIO(raw)).sheet_names)
        df = pd.read_excel(io.BytesIO(raw), sheet_name=sheet, dtype=str, keep_default_na=False)
    else:
        for enc in ("utf-8-sig", "cp1252"):
            try:
                df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, sep=None, engine="python", encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Não foi possível reconhecer a codificação do CSV.")
    if len(df) > 10000 or len(df.columns) > 100:
        raise ValueError("Limite de 10 mil linhas e 100 colunas.")
    if len(df.columns) < 3:
        raise ValueError("O arquivo deve conter pelo menos três colunas.")
    return df

def clean_xml_text(value):
    text = unicodedata.normalize('NFKD', str(value))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = text.replace('ß', 'ss').replace('Æ', 'AE').replace('æ', 'ae').replace('ø', 'o').replace('Ø', 'O')
    text = re.sub(r'[^A-Za-z0-9 /%.,+()_:\\-]', '', text)
    return text


def generate_xml(req, items, due_time, title, note, extra_name, extra_value):
    root = ET.Element("Pedido", {"layout": "WA"})
    header = ET.SubElement(root, "Cabecalho")
    for tag, value in (
        ("Requisicao", req), ("Titulo_Pdc", title), ("Id_Forma_Pagamento", "0"),
        ("Data_Vencimento", ""), ("Hora_Vencimento", due_time),
        ("Moeda", "Reais"), ("Observacao", note)
    ):
        ET.SubElement(header, tag).text = clean_xml_text(value)
    extra = ET.SubElement(header, "Campo_Extra")
    ET.SubElement(extra, "Nome").text = clean_xml_text(extra_name)
    ET.SubElement(extra, "Valor").text = clean_xml_text(extra_value)
    container = ET.SubElement(root, "Itens_Requisicao")
    for item in items.itertuples(index=False, name=None):
        node = ET.SubElement(container, "Item_Requisicao")
        for tag, value in zip(("Codigo_Produto", "Descricao_Produto", "Quantidade"), item):
            ET.SubElement(node, tag).text = clean_xml_text(value)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="iso-8859-1", xml_declaration=True, short_empty_elements=False)

if arquivo is not None:
    try:
        if tipo_entrada == "PDF (OCR)" and erp != "MV":
            st.stop()
        df = load_table(arquivo)
        if tipo_entrada == "PDF (OCR)":
            st.warning("OCR do MV: confira cada código, descrição e quantidade solicitada. Nunca use Cons. Méd. Mensal, Est. Atual ou Última compra como quantidade.")
            if df.empty:
                st.error("O OCR não conseguiu identificar linhas com segurança. Confira o PDF abaixo e preencha os itens manualmente na tabela de revisão. Não serão inventados códigos ou quantidades.")
            with st.expander("Visualizar página do PDF original para conferir", expanded=df.empty):
                import fitz
                from PIL import Image
                pdf_doc = fitz.open(stream=arquivo.getvalue(), filetype="pdf")
                for page_idx in range(min(pdf_doc.page_count, 15)):
                    page = pdf_doc[page_idx]
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    preview = Image.open(io.BytesIO(pix.tobytes("png"))).rotate(270, expand=True)
                    st.image(preview, caption=f"Página {page_idx + 1} — confira a orientação e os valores", use_container_width=True)
            st.caption("Se alguma linha não for reconhecida, acrescente-a manualmente na tabela abaixo.")
        a, b, c = st.columns(3)
        names = list(df.columns)
        with a:
            codigo = st.selectbox("Coluna do código do produto", names, index=0)
        with b:
            descricao = st.selectbox("Coluna da descrição", names, index=1)
        with c:
            quantidade = st.selectbox("Coluna da quantidade", names, index=2)
        if len({codigo, descricao, quantidade}) != 3:
            st.error("Escolha três colunas diferentes.")
            st.stop()
        items = df[[codigo, descricao, quantidade]].copy()
        items.columns = ["Código", "Descrição", "Quantidade"]
        items = items.fillna("")
        st.subheader("Revisar itens")
        st.caption("Você pode editar diretamente na tabela antes de gerar o XML. Acentos, cedilha e símbolos não permitidos serão removidos automaticamente apenas do XML.")
        reviewed = st.data_editor(items, hide_index=True, num_rows="dynamic", use_container_width=True, key="xml_editor")
        if tipo_entrada == "PDF (OCR)" and not df.empty:
            st.warning(f"O OCR encontrou {len(df)} item(ns). Confira no PDF se há mais itens e se todas as quantidades estão corretas.")
        cleaned = reviewed.copy()
        for col in cleaned.columns:
            cleaned[col] = cleaned[col].astype(str).str.strip()
        errors = []
        if not re.fullmatch(r"\d{2}:\d{2}", hora.strip()):
            errors.append("A hora deve estar no formato HH:MM.")
        else:
            hh, mm = map(int, hora.split(":"))
            if hh > 23 or mm > 59:
                errors.append("Hora inválida.")
        if not len(cleaned):
            errors.append("Inclua pelo menos um item.")
        for i, row in cleaned.iterrows():
            if not row["Código"] or not row["Descrição"]:
                errors.append(f"Linha {i + 2}: código e descrição são obrigatórios.")
            qty = row["Quantidade"].replace(",", ".")
            try:
                from decimal import Decimal
                value = Decimal(qty)
                if not value.is_finite() or value <= 0:
                    raise ValueError()
            except Exception:
                errors.append(f"Linha {i + 2}: quantidade inválida.")
        st.write(f"**Exemplo de código no XML:** {cleaned.iloc[0]['Código'] + (' ' + complemento.strip() if complemento.strip() else '') if len(cleaned) else '(sem itens)'}")
        st.write(f"**Itens:** {len(cleaned)}")
        if errors:
            for error in errors[:20]:
                st.error(error)
            st.download_button("Baixar XML", data=b"", disabled=True)
        else:
            xml_items = cleaned[["Código", "Descrição", "Quantidade"]].copy()
            if complemento.strip():
                xml_items["Código"] = xml_items["Código"] + " " + complemento.strip()
            try:
                xml_data = generate_xml("", xml_items, hora.strip(), titulo.strip(),
                                        observacao.strip(), campo_extra_nome.strip(), campo_extra_valor.strip())
            except UnicodeEncodeError:
                st.error("Há caracteres que não podem ser gravados em ISO-8859-1. Revise os textos.")
                st.stop()
            st.success("XML gerado. Confira o arquivo em ambiente de teste do GTPlan antes do uso definitivo.")
            st.download_button("Baixar XML", data=xml_data,
                               file_name="pedido_gtplan.xml",
                               mime="application/xml")
    except Exception as exc:
        st.error(f"Não foi possível processar a planilha: {exc}")
else:
    st.info("Envie um arquivo para começar. Não é necessário instalar programas.")
