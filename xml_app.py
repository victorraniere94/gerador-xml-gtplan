import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Gerador XML GTPlan", page_icon="📄", layout="wide")
st.markdown("""<style>
:root {color-scheme: dark;}
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"],
[data-testid="stHeader"], [data-testid="stMain"] {background-color:#0b1220 !important;color:#e5e7eb !important;}
[data-testid="stSidebar"], [data-testid="stSidebarContent"] {background-color:#111c2e !important;}
h1,h2,h3,p,label,span {color:inherit;}
div[data-testid="stFileUploader"], div[data-testid="stExpander"],
div[data-testid="stDataFrame"] {background-color:#111c2e !important;border:1px solid #34445e !important;border-radius:12px;}
div[data-testid="stFileUploaderDropzone"] {background-color:#16243a !important;}
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div,
textarea, input {background-color:#18263b !important;color:#f1f5f9 !important;border-color:#40516a !important;}
div[data-testid="stAlert"] {border-radius:12px;}
div.stDownloadButton button[kind="primary"] {background-color:#2563eb !important;color:white !important;}
</style>""",unsafe_allow_html=True)
st.markdown("""<style>.block-container{max-width:1200px;padding-top:2rem}h1{letter-spacing:-.03em}div[data-testid="stFileUploader"]{border:1px solid #cbd5e1;border-radius:12px;padding:12px}div.stDownloadButton button{border-radius:10px;font-weight:700}</style>""",unsafe_allow_html=True)
st.markdown("""<style>
/* Contraste consistente inclusive em controles do Streamlit */
[data-testid="stApp"] {color:#f1f5f9 !important;}
[data-testid="stApp"] label,
[data-testid="stApp"] label *,
[data-testid="stApp"] [data-testid="stWidgetLabel"],
[data-testid="stApp"] [data-testid="stWidgetLabel"] *,
[data-testid="stApp"] [role="radiogroup"] *,
[data-testid="stApp"] [data-testid="stFileUploader"] *,
[data-testid="stApp"] [data-testid="stExpander"] *,
[data-testid="stApp"] [data-testid="stMarkdownContainer"] {
  color:#f1f5f9 !important;
}
[data-testid="stApp"] [data-testid="stCaptionContainer"],
[data-testid="stApp"] [data-testid="stCaptionContainer"] * {color:#cbd5e1 !important;}
[data-testid="stFileUploaderDropzone"] {background:#18263b !important;border:1px dashed #64748b !important;}
[data-testid="stFileUploaderDropzone"] button {color:#f8fafc !important;background:#334155 !important;border-color:#64748b !important;}
[data-testid="stApp"] input, [data-testid="stApp"] textarea {color:#fff !important;}
[data-testid="stApp"] input::placeholder {color:#aebdd0 !important;opacity:1;}
[data-testid="stApp"] [data-testid="stAlert"] * {color:inherit;}
</style>""",unsafe_allow_html=True)
st.title("Gerador de XML")
st.caption("GTPlan  •  Layout WA  •  Conversão de Excel, CSV e PDF")
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
    col_comp, col_hora = st.columns([2, 1])
    with col_comp:
        complemento = st.text_input("Complemento do código dos produtos", placeholder="Ex.: POLICLINICA", help="Será acrescentado ao final de cada Codigo_Produto no XML.")
    with col_hora:
        hora = st.text_input("Hora de vencimento", value="15:41")
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
    text = unicodedata.normalize('NFKD', str(value))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = text.replace('ß', 'ss').replace('Æ', 'AE').replace('æ', 'ae').replace('ø', 'o').replace('Ø', 'O')
    text = re.sub(r'[^A-Za-z0-9 /%.,+()_:\\-]', '', text)
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
        st.markdown("### 3. Conferir produtos")
        st.caption(f"Arquivo: {arquivo.name} • {len(items)} itens identificados")
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
                xml_data = generate_xml("", xml_items, hora.strip(), titulo.strip(),
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
