import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Gerador XML GTPlan", page_icon="📄", layout="wide")
st.markdown("""<style>
:root { color-scheme: dark; }
[data-testid="stApp"], [data-testid="stAppViewContainer"], [data-testid="stMain"] {
  background: #0b1120 !important; color: #e7edf7 !important;
}
[data-testid="stHeader"] { background: rgba(11,17,32,.94) !important; }
[data-testid="stSidebar"], [data-testid="stSidebarContent"] { background: #101c30 !important; }
.block-container { max-width: 1180px; padding-top: 2.3rem; padding-bottom: 4rem; }
h1 { letter-spacing: -.045em; font-weight: 800 !important; }
h2,h3 { letter-spacing: -.025em; }
[data-testid="stApp"] label, [data-testid="stApp"] [data-testid="stWidgetLabel"],
[data-testid="stApp"] [data-testid="stMarkdownContainer"] { color: #e7edf7; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color: #aabbd3 !important; }
[data-testid="stFileUploader"], [data-testid="stExpander"],
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
  background: #111e33 !important; border: 1px solid #2b405e !important;
  border-radius: 16px !important;
}
[data-testid="stFileUploader"] { padding: 10px; }
[data-testid="stFileUploaderDropzone"] {
  background: #172740 !important; border: 1px dashed #5a81ad !important;
  border-radius: 12px !important;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: #67b8ff !important; }
[data-testid="stFileUploaderDropzone"] button {
  background: #263e5c !important; border: 1px solid #496d98 !important;
  color: #f8fbff !important; border-radius: 9px !important;
}
[data-baseweb="input"] > div, [data-baseweb="select"] > div,
[data-testid="stApp"] textarea, [data-testid="stApp"] input {
  background: #172740 !important; color: #f8fbff !important;
  border-color: #425b7b !important;
}
[data-testid="stApp"] input::placeholder { color: #b1c1d6 !important; opacity: 1; }
[data-testid="stAlert"] { border-radius: 12px !important; }
[data-testid="stMetric"] {
  background: #13233a; border: 1px solid #2c4667;
  border-radius: 13px; padding: 14px 18px;
}
div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {
  border-radius: 10px !important; font-weight: 700 !important;
  min-height: 42px;
}
div[data-testid="stDownloadButton"] button {
  background: #80c8fa !important; border: 1px solid #80c8fa !important;
  color: #091729 !important;
}
div[data-testid="stDownloadButton"] button * { color: #091729 !important; }
div[data-testid="stDownloadButton"] button[kind="primary"] {
  background: #22814d !important; border-color: #22814d !important;
  color: #fff !important;
}
div[data-testid="stDownloadButton"] button[kind="primary"] * { color: #fff !important; }
div[data-testid="stDownloadButton"] button:disabled {
  background: #344155 !important; color: #cbd5e1 !important;
}
div[data-testid="stDownloadButton"] button:disabled * { color: #cbd5e1 !important; }
.gt-hero {
  padding: 22px 26px; border: 1px solid #2b4769; border-radius: 18px;
  background: linear-gradient(115deg,#162943 0%,#101c31 75%);
  margin-bottom: 18px;
}
.gt-eyebrow { color: #7ec8ff; font-size: .76rem; font-weight: 800; letter-spacing: .14em; }
.gt-hero h1 { margin: 6px 0 4px; color: #f8fbff; font-size: clamp(1.8rem,3vw,2.6rem); }
.gt-hero p { color: #afc4dd; margin: 0; }
.gt-steps { display:flex; flex-wrap:wrap; gap:10px; margin: 8px 0 24px; }
.gt-step {
  flex:1; min-width:155px; padding:12px 15px; border-radius:12px;
  background:#13233a; border:1px solid #2b405e; color:#dbe8f7;
  font-size:.88rem; font-weight:600;
}
.gt-step b { color:#7ec8ff; margin-right:7px; }
@media(max-width:640px) {
  .block-container { padding: 1.2rem .9rem 3rem; }
  .gt-hero { padding:18px; }
  .gt-step { min-width:100%; }
}
</style>""", unsafe_allow_html=True)
st.markdown("""<div class="gt-hero">
<div class="gt-eyebrow">GTPLAN · LAYOUT WA</div>
<h1>Gerador de XML</h1>
<p>Converta requisições em XML com conferência dos produtos antes da exportação.</p>
</div>
<div class="gt-steps">
<div class="gt-step"><b>01</b> Enviar arquivo</div>
<div class="gt-step"><b>02</b> Conferir produtos</div>
<div class="gt-step"><b>03</b> Gerar XML</div>
</div>""", unsafe_allow_html=True)
st.info("Use somente arquivos autorizados. Este aplicativo é público. Confira os dados antes de importar no GTPlan.")
st.markdown("### 1. Origem do documento")

col_formato, col_erp = st.columns(2, gap="large")
with col_formato:
    tipo_entrada = st.radio("Formato do arquivo de origem", ["Excel / CSV", "PDF (OCR)"], horizontal=True)
with col_erp:
    if tipo_entrada == "PDF (OCR)":
        erp = st.radio("ERP de origem", ["MV", "SPData", "Syshosp", "SMED"], horizontal=True)
    else:
        erp = None
        st.caption("ERP de origem: não se aplica a Excel / CSV")

st.markdown("### 2. Enviar arquivo")
if tipo_entrada == "PDF (OCR)":
    arquivo = st.file_uploader("Enviar PDF da requisição (até 10 MB)", type=["pdf"], key="pdf_upload")
    if erp not in ("MV", "SPData", "Syshosp"):
        st.warning(f"A leitura automática do ERP {erp} ainda não foi configurada. Por enquanto, utilize MV, SPData, Syshosp ou Excel/CSV.")
else:
    arquivo = st.file_uploader("Importe Excel (.xlsx) ou CSV com código, descrição e quantidade (máximo 10 MB)", type=["xlsx", "csv"])
    st.caption("A quantidade deve ser a quantidade final solicitada, sem multiplicação por embalagem. Códigos e descrições são mantidos como texto.")

with st.expander("Configurações opcionais do XML", expanded=False):
    complemento = st.text_input("Complemento do código dos produtos", placeholder="Ex.: POLICLINICA", help="Será acrescentado ao final de cada Codigo_Produto no XML.")
# Campos fixos do layout WA, sem necessidade de preenchimento na interface.
titulo = ""
observacao = ""
campo_extra_nome = "Não Programada"
campo_extra_valor = ""

def load_table(upload):
    raw = upload.getvalue()
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("O arquivo ultrapassa 10 MB.")
    if upload.name.lower().endswith(".pdf"):
        if erp == "SPData":
            from spdata_reader import extract_spdata
            return extract_spdata(raw)
        if erp == "Syshosp":
            from syshosp_reader import extract_syshosp
            return extract_syshosp(raw)
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
    """Preserva a descrição literal; XML/ISO-8859-1 não exige retirar acentos."""
    text = str(value)
    # XML 1.0 não permite controles C0 (exceto tab, CR e LF).
    text = "".join(ch for ch in text if ord(ch) in (9, 10, 13) or ord(ch) >= 32)
    # Impede substituição silenciosa de caracteres incompatíveis com o layout.
    text.encode("iso-8859-1", errors="strict")
    return text


def parse_quantity(value):
    from decimal import Decimal
    raw = str(value).strip().replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    number = Decimal(raw)
    if not number.is_finite() or number <= 0:
        raise ValueError("Quantidade inválida")
    return format(number, "f")


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
        if tipo_entrada == "PDF (OCR)" and erp not in ("MV", "SPData", "Syshosp"):
            st.stop()
        with st.spinner("Lendo arquivo e identificando produtos... PDFs grandes podem demorar alguns minutos."):
            df = load_table(arquivo)
        if tipo_entrada == "PDF (OCR)":
            st.warning("Em PDFs grandes, o reconhecimento pode demorar alguns minutos. Confira todos os códigos, descrições e quantidades com o PDF original. No MV, use apenas Dados da Solicitação; no SPData e Syshosp, ignore Seq. e UND.")
            if df.empty:
                st.error("O OCR não conseguiu identificar linhas com segurança. Confira o PDF abaixo e preencha os itens manualmente na tabela de revisão. Não serão inventados códigos ou quantidades.")
            with st.expander("Visualizar páginas do PDF original para conferir", expanded=df.empty):
                import fitz
                from PIL import Image
                pdf_doc = fitz.open(stream=arquivo.getvalue(), filetype="pdf")
                for page_idx in range(min(pdf_doc.page_count, 100)):
                    page = pdf_doc[page_idx]
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    preview = Image.open(io.BytesIO(pix.tobytes("png")))
                    if erp == "MV" and preview.height > preview.width:
                        preview = preview.rotate(270, expand=True)
                    st.image(preview, caption=f"Página {page_idx + 1} — confira a orientação e os valores", use_container_width=True)
            st.caption("Se alguma linha não for reconhecida, acrescente-a manualmente na tabela abaixo.")
            if erp == "MV":
                sequencias = df.attrs.get("mv_sequences", [])
                if sequencias:
                    st.metric("Linhas com Seq. reconhecida pelo OCR", len(sequencias))
                    if len(sequencias) != len(df):
                        st.warning(f"MV: {len(sequencias)} sequências legíveis e {len(df)} itens extraídos. Seq. pode falhar no OCR; confira a contagem de produtos no PDF.")
                if sequencias:
                    from collections import Counter
                    por_pagina = Counter(pagina for pagina, seq in sequencias)
                    with st.expander("Diagnóstico MV — sequências reconhecidas por página"):
                        st.caption("Esta contagem mostra as linhas identificadas pelo OCR, não garante que a descrição e a quantidade estejam corretas.")
                        st.dataframe(pd.DataFrame([{"Página": p, "Sequências identificadas": por_pagina.get(p, 0)} for p in range(1, max(por_pagina) + 1)]), hide_index=True, use_container_width=True)
                        nums = {seq for _, seq in sequencias}
                        if nums and max(nums) <= 500:
                            ausentes = sorted(set(range(1, max(nums) + 1)) - nums)
                            if ausentes:
                                st.caption("Números de sequência não reconhecidos com segurança (não representam necessariamente produtos ausentes): " + ", ".join(map(str, ausentes)))
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
        if tipo_entrada == "PDF (OCR)" and erp == "MV" and not df.empty:
            st.download_button("Baixar conferência dos itens identificados (CSV)", data=df.to_csv(index=False, sep=";").encode("utf-8-sig"), file_name="conferencia_mv.csv", mime="text/csv")
        st.markdown("### 3. Conferir produtos")
        st.caption(f"Arquivo: {arquivo.name} • {len(items)} itens identificados")
        st.caption("Você pode editar diretamente na tabela antes de gerar o XML. As descrições serão mantidas exatamente como aparecem na tabela, inclusive acentos e espaços.")
        reviewed = st.data_editor(items, hide_index=True, num_rows="dynamic", use_container_width=True, key="xml_editor")
        if tipo_entrada == "PDF (OCR)" and not df.empty:
            st.warning(f"O OCR encontrou {len(df)} item(ns). Confira no PDF se há mais itens e se todas as quantidades estão corretas.")
        cleaned = reviewed.copy()
        for col in cleaned.columns:
            cleaned[col] = cleaned[col].astype(str)
        # Descrições oficiais podem conter espaços significativos no final.
        cleaned["Código"] = cleaned["Código"].str.strip()
        cleaned["Quantidade"] = cleaned["Quantidade"].str.strip()
        errors = []
        if not len(cleaned):
            errors.append("Inclua pelo menos um item.")
        for i, row in cleaned.iterrows():
            if not row["Código"] or not row["Descrição"]:
                errors.append(f"Linha {i + 2}: código e descrição são obrigatórios.")
            try:
                parse_quantity(row["Quantidade"])
            except Exception:
                errors.append(f"Linha {i + 2}: quantidade inválida.")
        st.write(f"**Exemplo de código no XML:** {cleaned.iloc[0]['Código'] + (' ' + complemento.strip() if complemento.strip() else '') if len(cleaned) else '(sem itens)'}")
        st.write(f"**Itens:** {len(cleaned)}")
        if tipo_entrada == "PDF (OCR)":
            total_esperado = st.number_input("Quantos produtos constam no PDF original?", min_value=1, value=max(1, len(cleaned)), step=1, help="Conte os itens de todas as páginas, não as linhas da descrição.")
            if len(cleaned) != total_esperado:
                errors.append(f"O PDF tem {total_esperado} produtos, mas a tabela contém {len(cleaned)}. Corrija antes de gerar o XML.")
            confirmado = st.checkbox("Conferi todos os códigos, descrições e quantidades com o PDF original.", value=False)
            if not confirmado:
                errors.append("Confirme a conferência dos itens antes de baixar o XML.")
        st.markdown("### 4. Gerar XML")
        if errors:
            for error in errors[:20]:
                st.error(error)
            st.download_button("Baixar XML", data=b"", disabled=True, use_container_width=True)
        else:
            xml_items = cleaned[["Código", "Descrição", "Quantidade"]].copy()
            if complemento.strip():
                xml_items["Código"] = xml_items["Código"] + " " + complemento.strip()
            xml_items["Quantidade"] = xml_items["Quantidade"].map(parse_quantity)
            try:
                xml_data = generate_xml("", xml_items, "", titulo.strip(),
                                        observacao.strip(), campo_extra_nome.strip(), campo_extra_valor.strip())
            except UnicodeEncodeError:
                st.error("Há caracteres que não podem ser gravados em ISO-8859-1. Revise os textos.")
                st.stop()
            st.success("XML gerado. Confira o arquivo em ambiente de teste do GTPlan antes do uso definitivo.")
            st.download_button("Baixar XML", data=xml_data,
                               file_name="pedido_gtplan.xml",
                               mime="application/xml", use_container_width=True, type="primary")
    except Exception as exc:
        st.error(f"Não foi possível processar a planilha: {exc}")
else:
    st.info("Envie um arquivo para começar. Não é necessário instalar programas.")
