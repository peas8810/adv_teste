import streamlit as st
import datetime
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from fpdf import FPDF
from docx import Document
from dotenv import load_dotenv
import os
import plotly.express as px
import streamlit.components.v1 as components
import io

# -------------------- Configurações Iniciais --------------------
load_dotenv()
st.set_page_config(page_title="Sistema Jurídico", layout="wide")

# API & Planilha
GAS_WEB_APP_URL = os.getenv(
    "GAS_WEB_APP_URL",
    "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"
)

# -------------------- Funções Auxiliares --------------------
@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados_da_planilha(tipo: str, debug: bool = False) -> list:
    """Retorna lista de registros JSON da aba especificada."""
    try:
        resp = httpx.get(GAS_WEB_APP_URL, params={"tipo": tipo}, timeout=10)
        resp.raise_for_status()
        if debug:
            st.text(f"URL chamada: {resp.url}")
            st.text(f"Resposta: {resp.text[:200]}")
        return resp.json()
    except httpx.HTTPStatusError as e:
        st.error(f"Erro de status HTTP ({tipo}): {e.response.status_code} - {e}")
    except httpx.RequestError as e:
        st.error(f"Erro de requisição ({tipo}): {e}")
    except ValueError as e:
        st.error(f"Resposta inválida ({tipo}): {e}")
    return []

@st.cache_data(ttl=300)
def carregar_usuarios_da_planilha() -> dict:
    """Carrega e retorna dicionário de usuários."""
    funcs = carregar_dados_da_planilha("Funcionario") or []
    if not funcs:
        return {"dono": {"username": "dono", "senha": "dono123", "papel": "owner", "escritorio": "Global", "area": "Todas"}}
    users = {}
    for f in funcs:
        key = f.get("usuario")
        if not key:
            continue
        users[key] = {
            "username": key,
            "senha": f.get("senha", ""),
            "papel": f.get("papel", "assistant"),
            "escritorio": f.get("escritorio", "Global"),
            "area": f.get("area", "Todas"),
        }
    return users

@st.cache_data(ttl=300)
def converter_data(data_str: str) -> datetime.date:
    if not data_str:
        return datetime.date.today()
    try:
        ds = data_str.rstrip("Z")
        if "T" in ds:
            return datetime.datetime.fromisoformat(ds).date()
        return datetime.date.fromisoformat(ds)
    except Exception:
        return datetime.date.today()

@st.cache_data(ttl=300)
def calcular_status_processo(data_prazo: datetime.date, houve_mov: bool, encerrado: bool=False) -> str:
    if encerrado:
        return "⚫ Encerrado"
    dias = (data_prazo - datetime.date.today()).days
    if houve_mov:
        return "🔵 Movimentado"
    if dias < 0:
        return "🔴 Atrasado"
    if dias <= 10:
        return "🟡 Atenção"
    return "🟢 Normal"


def enviar_dados_para_planilha(tipo: str, dados: dict) -> bool:
    """Envia JSON via POST e retorna True se texto == 'OK'."""
    try:
        resp = httpx.post(GAS_WEB_APP_URL, json={"tipo": tipo, **dados}, timeout=10)
        if resp.text.strip() == "OK":
            return True
        st.error(f"Erro de envio: {resp.text}")
    except httpx.RequestError as e:
        st.error(f"Falha ao enviar ({tipo}): {e}")
    return False


def exportar_pdf(texto: str, nome: str) -> str:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, texto)
    path = f"{nome}.pdf"
    pdf.output(path)
    return path


def exportar_docx(texto: str, nome: str) -> str:
    doc = Document()
    doc.add_paragraph(texto)
    path = f"{nome}.docx"
    doc.save(path)
    return path


def exportar_csv(dados: list, nome: str) -> bytes:
    df = pd.DataFrame(dados)
    return df.to_csv(index=False).encode("utf-8")


def consultar_movimentacoes_simples(numero: str) -> list:
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={numero}"
    try:
        r = httpx.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        trs = soup.select("tr.fundocinza1")
        return [tr.get_text(strip=True) for tr in trs[:5]] or ["Nenhuma movimentação"]
    except Exception:
        return ["Erro na consulta TJSP"]

# -------------------- UI: TELAS --------------------
def tela_dashboard(clientes, processos):
    st.subheader("📋 Painel de Processos")
    area_fixa = st.session_state.area_fixa
    with st.expander("Filtros", expanded=True):
        col1, col2, col3 = st.columns(3)
        filtro_area = area_fixa or col1.selectbox(
            "Área", ["Todas"] + sorted({p.get("area") for p in processos})
        )
        filtro_status = col2.selectbox(
            "Status", ["Todos", "🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado", "⚫ Encerrado"]
        )
        filtro_esc = col3.selectbox(
            "Escritório", ["Todos"] + sorted({p.get("escritorio") for p in processos})
        )
    vis = []
    for p in processos:
        if filtro_area != "Todas" and p.get("area") != filtro_area: continue
        if filtro_esc != "Todos" and p.get("escritorio") != filtro_esc: continue
        status = calcular_status_processo(
            converter_data(p.get("prazo")), p.get("houve_movimentacao", False), p.get("encerrado", False)
        )
        if filtro_status != "Todos" and status != filtro_status: continue
        vis.append({**p, "status_calc": status})

    # Métricas
    total = len(vis)
    st.metric("Total", total)
    # ... (outras métricas conforme necessidade)

    # Tabela
    if vis:
        df = pd.DataFrame(vis)
        df = df.rename(columns={"status_calc": "Status"})
        st.dataframe(df)
    else:
        st.info("Nenhum processo encontrado.")


def tela_clientes(clientes):
    st.subheader("👥 Clientes")
    with st.form("form_cliente"):
        nome = st.text_input("Nome*")
        email = st.text_input("E-mail*")
        telefone = st.text_input("Telefone*")
        if st.form_submit_button("Salvar"):
            if not all([nome, email, telefone]):
                st.warning("Preencha campos obrigatórios.")
            else:
                ok = enviar_dados_para_planilha("Cliente", {"nome": nome, "email": email, "telefone": telefone})
                st.success("Cliente salvo." if ok else "Erro ao salvar.")
    if clientes:
        st.dataframe(pd.DataFrame(clientes))
        if st.button("Exportar CSV Clientes"):
            st.download_button(
                "Baixar CSV", exportar_csv(clientes, "clientes"), "clientes.csv", "text/csv"
            )
    else:
        st.info("Sem clientes cadastrados.")


def tela_leads(leads):
    st.subheader("📇 Leads")
    with st.form("form_lead"):
        nome = st.text_input("Nome*")
        contato = st.text_input("Contato*")
        if st.form_submit_button("Salvar"):
            if not all([nome, contato]):
                st.warning("Campos obrigatórios.")
            else:
                enviar_dados_para_planilha("Lead", {"nome": nome, "numero": contato})
                st.success("Lead salvo.")
    if leads:
        st.dataframe(pd.DataFrame(leads))
    else:
        st.info("Sem leads.")


def tela_processos(processos):
    st.subheader("📄 Processos")
    with st.form("form_proc"):
        num = st.text_input("Número*")
        cliente = st.text_input("Cliente*")
        if st.form_submit_button("Salvar"):
            if not all([num, cliente]): st.warning("Campos obrigatórios.")
            else:
                enviar_dados_para_planilha("Processo", {"numero": num, "cliente": cliente})
                st.success("Processo salvo.")
    if processos:
        st.dataframe(pd.DataFrame(processos))
    else:
        st.info("Sem processos.")


def tela_historicos(hist):
    st.subheader("📜 Históricos e TJMG")
    num = st.text_input("Num. Processo")
    if num:
        encontrados = [h for h in hist if h.get("numero") == num]
        st.write(encontrados or "Nenhum histórico.")
    st.components.v1.html(
        "<iframe src='https://www.tjmg.jus.br/portal-tjmg/processos/andamento-processual/'"
        " style='width:100%; height:600px; border:none;'></iframe>", height=600
    )


def tela_relatorios(processos, escritorios):
    st.subheader("📊 Relatórios")
    tipo = st.selectbox("Tipo", ["Processos", "Escritórios"])
    formato = st.selectbox("Formato", ["PDF", "DOCX", "CSV"])
    data = processos if tipo == "Processos" else escritorios
    if st.button("Gerar Relatório"):
        if formato == "CSV":
            st.download_button("Baixar CSV", exportar_csv(data, tipo.lower()), f"{tipo}.csv", "text/csv")
        else:
            texto = "\n".join(str(r) for r in data)
            if formato == "PDF": path = exportar_pdf(texto, tipo.lower())
            else: path = exportar_docx(texto, tipo.lower())
            with open(path, "rb") as f:
                st.download_button("Baixar", f, file_name=os.path.basename(path))


def tela_gerenciar_funcionarios(funcs):
    st.subheader("👥 Funcionários")
    # Similar a clientes
    st.dataframe(pd.DataFrame(funcs))


def tela_gerenciar_escritorios(escs):
    st.subheader("🏢 Escritórios")
    st.dataframe(pd.DataFrame(escs))


def tela_gerenciar_permissoes(funcs):
    st.subheader("🔧 Permissões")
    st.dataframe(pd.DataFrame(funcs))

# -------------------- MAIN --------------------
def main():
    st.session_state.USERS = carregar_usuarios_da_planilha()
    CLIENTES = carregar_dados_da_planilha("Cliente")
    PROCESSOS = carregar_dados_da_planilha("Processo")
    ESCR = carregar_dados_da_planilha("Escritorio")
    HIST = carregar_dados_da_planilha("Historico_Peticao")
    LEADS = carregar_dados_da_planilha("Lead")

    # Login
    with st.sidebar:
        st.header("🔐 Login")
        usr = st.text_input("Usuário")
        pwd = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = st.session_state.USERS.get(usr)
            if user and user.get("senha") == pwd:
                st.session_state.usuario = usr
                st.session_state.papel = user.get("papel")
                st.session_state.area_fixa = None if user.get("area") == "Todas" else user.get("area")
                st.success("Logado!")
            else:
                st.error("Credenciais inválidas.")
        if st.session_state.get("usuario") and st.button("Sair"):
            for k in ["usuario","papel","area_fixa"]: st.session_state.pop(k, None)
            st.experimental_rerun()

    if not st.session_state.get("usuario"):
        st.info("Faça login para continuar.")
        return

    st.sidebar.success(f"Usuário: {st.session_state.usuario}")
    menu = ["Dashboard","Clientes","Leads","Processos","Históricos"]
    if st.session_state.papel in ["owner","manager"]:
        menu.append("Relatórios")
    if st.session_state.papel in ["manager","owner"]:
        menu.append("Gerenciar Funcionários")
    if st.session_state.papel == "owner":
        menu.extend(["Gerenciar Escritórios","Gerenciar Permissões"])
    escolha = st.sidebar.selectbox("Menu", menu)

    # Chamadas de tela
    if escolha == "Dashboard":
        tela_dashboard(CLIENTES, PROCESSOS)
    elif escolha == "Clientes":
        tela_clientes(CLIENTES)
    elif escolha == "Leads":
        tela_leads(LEADS)
    elif escolha == "Processos":
        tela_processos(PROCESSOS)
    elif escolha == "Históricos":
        tela_historicos(HIST)
    elif escolha == "Relatórios":
        tela_relatorios(PROCESSOS, ESCR)
    elif escolha == "Gerenciar Funcionários":
        tela_gerenciar_funcionarios(carregar_dados_da_planilha("Funcionario"))
    elif escolha == "Gerenciar Escritórios":
        tela_gerenciar_escritorios(ESCR)
    elif escolha == "Gerenciar Permissões":
        tela_gerenciar_permissoes(carregar_dados_da_planilha("Funcionario"))

if __name__ == "__main__":
    main()
