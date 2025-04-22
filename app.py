import streamlit as st
import datetime
import time
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
st.set_page_config(page_title="Sistema Jurídico - Fernanda Freitas", layout="wide")
load_dotenv()

# Configuração da API DeepSeek e do Google Apps Script
GAS_WEB_APP_URL = (
    "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-"
    "rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"
)

# -------------------- Usuários Persistidos --------------------
USUARIOS_FIXOS = {
    "dono": {"username": "dono", "senha": "dono123", "papel": "owner", "escritorio": "Global", "area": "Todas"},
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
def carregar_dados_da_planilha(tipo, debug=False, retries=3, timeout=30):
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo}, timeout=timeout)
            response.raise_for_status()
            if debug:
                st.text(f"[DEBUG] Tentativa {attempt} — URL: {response.url}")
                st.text(f"[DEBUG] Resposta (primeiros 500 chars): {response.text[:500]}")
            return response.json()
        except requests.exceptions.ReadTimeout:
            if attempt < retries:
                st.warning(f"Timeout ao carregar '{tipo}', tentativa {attempt}/{retries}. Retentando em 2 s…")
                time.sleep(2)
                continue
            st.error(f"Timeout ao carregar dados ('{tipo}') após {retries} tentativas.")
            return []
        except Exception as e:
            st.error(f"Erro ao carregar dados ('{tipo}'): {e}")
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


def carregar_usuarios_da_planilha():
    funcionarios = carregar_dados_da_planilha("Funcionario") or []
    users = {}
    for f in funcionarios:
        chave = f.get("usuario")
        if not chave:
            continue
        users[chave] = {
            "username": chave,
            "senha": f.get("senha", ""),
            "papel": f.get("papel", "assistant"),
            "escritorio": f.get("escritorio", "Global"),
            "area": f.get("area", "Todas")
        }
    return users


def login(usuario, senha):
    user = st.session_state.USERS.get(usuario)
    if user and user.get("senha") == senha:
        return user
    return None


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


def consultar_movimentacoes_simples(numero):
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={numero}"
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


def buscar_processo_por_numero(numero, processos):
    for p in processos:
        if p.get("numero") == numero:
            return p
    return None


def inicializar_usuarios():
    base = USUARIOS_FIXOS.copy()
    base.update(carregar_usuarios_da_planilha())
    return base


def main():
    st.title("Sistema Jurídico - Fernanda Freitas")
    if "USERS" not in st.session_state:
        st.session_state.USERS = inicializar_usuarios()

    # Carrega abas
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HIST_PET = carregar_dados_da_planilha("Historico_Peticao") or []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []
    LEADS = carregar_dados_da_planilha("Lead") or []

    # Sidebar Login
    with st.sidebar:
        st.header("🔐 Login")
        user_in = st.text_input("Usuário")
        pass_in = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            u = login(user_in, pass_in)
            if u:
                st.session_state.usuario = user_in
                st.session_state.papel = u["papel"]
                st.session_state.dados_usuario = u
                st.success("Login realizado com sucesso!")
            else:
                st.error("Credenciais inválidas")
    if "usuario" in st.session_state:
        if st.sidebar.button("Sair"):
            for k in ["usuario", "papel", "dados_usuario"]:
                st.session_state.pop(k, None)
            st.sidebar.success("Você saiu do sistema!")
            st.experimental_rerun()

    # Conteúdo
    if "usuario" not in st.session_state:
        st.info("Por favor, faça login para acessar.")
        return

    papel = st.session_state.papel
    esc_user = st.session_state.dados_usuario.get("escritorio", "Global")
    area_user = st.session_state.dados_usuario.get("area", "Todas")
    st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")
    area_fixa = area_user if area_user != "Todas" else None

    opcoes = ["Dashboard", "Clientes", "Processos", "Históricos", "Gerenciar Funcionários"]
    if papel == "owner":
        opcoes += ["Gerenciar Escritórios", "Gerenciar Permissões"]
    escolha = st.sidebar.selectbox("Menu", opcoes)

    # Blocos de menu (Dashboard, Clientes, Processos, Históricos já implementados)
    # Gerenciar Funcionários
    if escolha == "Gerenciar Funcionários":
        st.subheader("👥 Cadastro de Funcionários")
        with st.form("form_funcionario"):
            nome = st.text_input("Nome Completo*")
            email = st.text_input("E-mail*")
            telefone = st.text_input("Telefone*")
            usuario_novo = st.text_input("Usuário*")
            senha_novo = st.text_input("Senha*", type="password")
            escritorio = st.selectbox("Escritório*", [e["nome"] for e in ESCRITORIOS] or ["Global"])
            area_atuacao = st.selectbox(
                "Área de Atuação*", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário", "Todas"]
            )
            papel_func = st.selectbox("Papel no Sistema*", ["manager", "lawyer", "assistant"])
            if st.form_submit_button("Cadastrar Funcionário"):
                if not (nome and email and telefone and usuario_novo and senha_novo):
                    st.warning("Campos obrigatórios não preenchidos!")
                else:
                    novo = {
                        "nome": nome,
                        "email": email,
                        "telefone": telefone,
                        "usuario": usuario_novo,
                        "senha": senha_novo,
                        "escritorio": escritorio,
                        "area": area_atuacao,
                        "papel": papel_func,
                        "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "cadastrado_por": st.session_state.usuario
                    }
                    if enviar_dados_para_planilha("Funcionario", novo):
                        st.success("Funcionário cadastrado com sucesso!")
                        FUNCIONARIOS.append(novo)
        st.subheader("Lista de Funcionários")
        if FUNCIONARIOS:
            df = get_dataframe_with_cols(funcionarios := FUNCIONARIOS, ["nome", "email", "telefone", "usuario", "papel", "escritorio", "area"] )
            st.dataframe(df)
        else:
            st.info("Nenhum funcionário cadastrado ainda")

    # Gerenciar Escritórios (owner)
    elif escolha == "Gerenciar Escritórios" and papel == "owner":
        st.subheader("🏢 Gerenciamento de Escritórios")
        tab1, tab2 = st.tabs(["Cadastrar Escritório", "Lista de Escritórios"])
        with tab1:
            with st.form("form_escritorio"):
                nome = st.text_input("Nome do Escritório*")
                endereco = st.text_input("Endereço Completo*")
                telefone = st.text_input("Telefone*")
                email = st.text_input("E-mail*")
                cnpj = st.text_input("CNPJ*")
                if st.form_submit_button("Salvar Escritório"):
                    if not (nome and endereco and telefone and email and cnpj):
                        st.warning("Todos os campos obrigatórios devem ser preenchidos!")
                    else:
                        novo = {"nome": nome, "endereco": endereco, "telefone": telefone, "email": email, "cnpj": cnpj}
                        if enviar_dados_para_planilha("Escritorio", novo):
                            st.success("Escritório cadastrado com sucesso!")
        with tab2:
            escs = carregar_dados_da_planilha("Escritorio") or []
            if escs:
                df = get_dataframe_with_cols(escs, ["nome", "endereco", "telefone", "email", "cnpj"] )
                st.dataframe(df)
            else:
                st.info("Nenhum escritório cadastrado ainda")

    # Gerenciar Permissões (owner)
    elif escolha == "Gerenciar Permissões" and papel == "owner":
        st.subheader("🔧 Gerenciar Permissões de Funcionários")
        if not FUNCIONARIOS:
            st.info("Nenhum funcionário cadastrado.")
        else:
            df = pd.DataFrame(FUNCIONARIOS)
            st.dataframe(df)
            sel = st.selectbox("Funcionário", df["nome"]) 
            areas = st.multiselect("Áreas Permitidas", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"] )
            if st.button("Atualizar Permissões"):
                for f in FUNCIONARIOS:
                    if f["nome"] == sel:
                        f["area"] = ", ".join(areas)
                        enviar_dados_para_planilha("Funcionario", {"usuario": f["usuario"], "area": f["area"], "atualizar": True})
                st.success("Permissões atualizadas com sucesso!")

if __name__ == '__main__':
    main()
