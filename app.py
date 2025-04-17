import streamlit as st
import datetime
import httpx
import requests
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from fpdf import FPDF
from docx import Document
import plotly.express as px

# -------------------- Configurações Iniciais --------------------
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configuração da API DeepSeek e do Google Apps Script
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-590cfea82f49426c94ff423d41a91f49")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# -------------------- Usuários Persistidos --------------------
if "USERS" not in st.session_state:
    st.session_state.USERS = {
        "dono": {"username": "dono", "senha": "dono123", "papel": "owner"},
        "gestor1": {"username": "gestor1", "senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A", "area": "Todas"},
        "adv1": {"username": "adv1", "senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Criminal"}
    }

# -------------------- Funções Auxiliares --------------------
def converter_data(data_str):
    if not data_str:
        return datetime.date.today()
    try:
        data_str = data_str.replace("Z", "")
        if "T" in data_str:
            return datetime.datetime.fromisoformat(data_str).date()
        return datetime.date.fromisoformat(data_str)
    except Exception:
        return datetime.date.today()

@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados_da_planilha(tipo, debug=False):
    try:
        response = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo}, timeout=10)
        response.raise_for_status()
        if debug:
            st.text(f"URL chamada: {response.url}")
            st.text(f"Resposta bruta: {response.text[:500]}")
        return response.json()
    except Exception as e:
        st.error(f"Erro ao carregar dados ({tipo}): {e}")
        return []

def enviar_dados_para_planilha(tipo, dados):
    try:
        payload = {"tipo": tipo, **dados}
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            response = client.post(GAS_WEB_APP_URL, json=payload)
        if response.text.strip() == "OK":
            return True
        st.error(f"Erro no envio: {response.text}")
        return False
    except Exception as e:
        st.error(f"Erro ao enviar dados ({tipo}): {e}")
        return False

@st.cache_data(ttl=300)
def carregar_usuarios_da_planilha():
    funcionarios = carregar_dados_da_planilha("Funcionario") or []
    if not funcionarios:
        return {"dono": {"username": "dono", "senha": "dono123", "papel": "owner", "escritorio": "Global", "area": "Todas"}}
    users = {}
    for f in funcionarios:
        key = f.get("usuario")
        if not key:
            continue
        users[key] = {
            "username": key,
            "senha": f.get("senha", ""),
            "papel": f.get("papel", "assistant"),
            "escritorio": f.get("escritorio", "Global"),
            "area": f.get("area", "Todas")
        }
    return users


def login(usuario, senha):
    user = st.session_state.USERS.get(usuario)
    return user if user and user.get("senha") == senha else None


def calcular_status_processo(data_prazo, houve_movimentacao, encerrado=False):
    if encerrado:
        return "⚫ Encerrado"
    hoje = datetime.date.today()
    dias = (data_prazo - hoje).days
    if houve_movimentacao:
        return "🔵 Movimentado"
    if dias < 0:
        return "🔴 Atrasado"
    if dias <= 10:
        return "🟡 Atenção"
    return "🟢 Normal"


def consultar_movimentacoes_simples(numero_processo):
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={numero_processo}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        andamentos = soup.find_all("tr", class_="fundocinza1")
        return [a.get_text(strip=True) for a in andamentos[:5]] if andamentos else ["Nenhuma movimentação encontrada"]
    except:
        return ["Erro ao consultar movimentações"]


def exportar_pdf(texto, nome_arquivo="relatorio"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, texto)
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"


def exportar_docx(texto, nome_arquivo="relatorio"):
    doc = Document()
    doc.add_paragraph(texto)
    doc.save(f"{nome_arquivo}.docx")
    return f"{nome_arquivo}.docx"


def gerar_relatorio_pdf(dados, nome_arquivo="relatorio"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Relatório de Processos", ln=1, align='C')
    pdf.ln(10)
    headers = ["Cliente", "Número", "Área", "Status", "Responsável"]
    widths = [40, 30, 50, 30, 40]
    for h, w in zip(headers, widths): pdf.cell(w, 10, txt=h, border=1)
    pdf.ln()
    for p in dados:
        status = calcular_status_processo(converter_data(p.get("prazo")), p.get("houve_movimentacao", False), p.get("encerrado", False))
        cols = [p.get("cliente", ""), p.get("numero", ""), p.get("area", ""), status, p.get("responsavel", "")]
        for v, w in zip(cols, widths): pdf.cell(w, 10, txt=str(v), border=1)
        pdf.ln()
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"


def aplicar_filtros(dados, filtros):
    def extrar(r): ds = r.get("data_cadastro") or r.get("cadastro"); return None if not ds else datetime.date.fromisoformat(ds[:10])
    res = []
    for r in dados:
        ok, dr = True, extrar(r)
        for c, v in filtros.items():
            if not v: continue
            if c == "data_inicio" and (dr is None or dr < v): ok = False; break
            if c == "data_fim" and (dr is None or dr > v): ok = False; break
            if c not in ["data_inicio", "data_fim"] and v.lower() not in str(r.get(c, "")).lower(): ok = False; break
        if ok: res.append(r)
    return res


def atualizar_processo(numero_processo, atualizacoes):
    atualizacoes["numero"] = numero_processo; atualizacoes["atualizar"]=True
    return enviar_dados_para_planilha("Processo", atualizacoes)

def excluir_processo(numero_processo):
    return enviar_dados_para_planilha("Processo", {"numero": numero_processo, "excluir": True})


def get_dataframe_with_cols(data, cols):
    df = pd.DataFrame(data if isinstance(data, list) else [data])
    for c in cols: df[c] = df.get(c, "")
    return df[cols]

##############################
# Interface Principal
##############################
def main():
    st.title("Sistema Jurídico")
    st.session_state.USERS = carregar_usuarios_da_planilha()
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HISTORICO = carregar_dados_da_planilha("Historico_Peticao") or []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []
    LEADS = carregar_dados_da_planilha("Lead") or []

    with st.sidebar:
        st.header("🔐 Login")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = login(usuario, senha)
            if user:
                st.session_state.usuario = usuario; st.session_state.papel = user.get("papel"); st.session_state.dados_usuario = user; st.success("Login realizado com sucesso!")
            else: st.error("Credenciais inválidas")
        if st.session_state.get("usuario") and st.button("Sair"):
            for k in ["usuario","papel","dados_usuario"]: st.session_state.pop(k,None)
            st.sidebar.success("Você saiu do sistema!"); st.experimental_rerun()

    if not st.session_state.get("usuario"): st.info("Por favor, faça login para acessar o sistema."); return

    papel = st.session_state.papel; esc = st.session_state.dados_usuario.get("escritorio","Global"); area = st.session_state.dados_usuario.get("area","Todas")
    st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")

    menu=["Dashboard","Clientes","Gestão de Leads","Processos","Históricos"]
    if papel in ["owner","manager"]: menu.append("Relatórios")
    if papel=="manager": menu.append("Gerenciar Funcionários")
    if papel=="owner": menu.extend(["Gerenciar Escritórios","Gerenciar Permissões"])
    escolha=st.sidebar.selectbox("Menu",menu)

    if escolha=="Dashboard":
        # Dashboard completo como antes (métricas, aniversariantes, gráfico, lista de processos)
        pass  # inserir conforme código anterior

    elif escolha=="Clientes":
        # Cadastro e lista com export TXT/PDF conforme código anterior
        pass

    elif escolha=="Gestão de Leads":
        # Formulário e lista com exportações TXT/PDF
        pass

    elif escolha=="Processos":
        # Formulário e lista com exportações TXT/PDF
        pass

    elif escolha=="Históricos":
        # Histórico + iframe TJMG
        pass

    elif escolha=="Relatórios" and papel in ["owner","manager"]:
        # Relatórios personalizados para todos os tipos com export PDF/DOCX/CSV
        pass

    elif escolha=="Gerenciar Funcionários":
        # Cadastro e lista com export TXT/PDF
        pass

    elif escolha=="Gerenciar Escritórios" and papel=="owner":
        # Cadastrar, listar e administradores
        pass

    elif escolha=="Gerenciar Permissões" and papel=="owner":
        # Atualizar áreas de funcionários
        pass

if __name__=="__main__": main()
