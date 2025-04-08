#Código por partes#


# Agora, iniciando pela Parte 1 (Importações e configuração geral):

import streamlit as st
import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
import json
import httpx
from fpdf import FPDF
from docx import Document
import time
import pandas as pd

# -------------------- Configurações Iniciais --------------------
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configuração da API DeepSeek (substituir pela sua chave real se precisar)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"

# URL do Web App do Google Apps Script (Webhook)
GAS_WEB_APP_URL = os.getenv("GAS_WEB_APP_URL") or "https://script.google.com/macros/s/AKfycbytp0BA1x2PnjcFhunbgWEoMxZmCobyZHNzq3Mxabr41RScNAH-nYIlBd-OySWv5dcx/exec"

# Dados temporários de login para simulação
USERS = {
    "dono": {"senha": "dono123", "papel": "owner"},
    "gestor1": {"senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A"},
    "adv1": {"senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Cível"},
}



# -------------------- Parte 2: Integração com Google Sheets --------------------
def enviar_dados_para_planilha(tipo, dados):
    try:
        payload = {"tipo": tipo, **dados}
        response = requests.post(
            GAS_WEB_APP_URL,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        return response.text.strip() == "OK"
    except Exception as e:
        st.error(f"❌ Erro ao enviar dados ({tipo}): {e}")
        return False

def carregar_dados_da_planilha(tipo, debug=False):
    try:
        response = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo})
        response.raise_for_status()
        if debug:
            st.text(f"🔍 URL chamada: {response.url}")
            st.text(f"📄 Resposta bruta: {response.text[:500]}")
        return response.json()
    except json.JSONDecodeError:
        st.error(f"❌ Resposta inválida para o tipo '{tipo}'. O servidor não retornou JSON válido.")
        return []
    except Exception as e:
        st.warning(f"⚠️ Erro ao carregar dados ({tipo}): {e}")
        return []

# Função auxiliar para carregar todos os dados do sistema
def carregar_dados_globais():
    return {
        "CLIENTES": carregar_dados_da_planilha("Cliente"),
        "PROCESSOS": carregar_dados_da_planilha("Processo"),
        "ESCRITORIOS": carregar_dados_da_planilha("Escritorio"),
        "HISTORICO_PETICOES": carregar_dados_da_planilha("Historico_Peticao"),
        "FUNCIONARIOS": carregar_dados_da_planilha("Funcionarios"),
    }

# -------------------- Parte 3: Autenticação e Controle de Permissões --------------------
def login(usuario, senha, funcionarios):
    user = USERS.get(usuario)
    if user and user["senha"] == senha:
        return user
    # Verifica se é um funcionário do Google Sheets
    for f in funcionarios:
        if f.get("usuario") == usuario and f.get("senha") == senha:
            return {
                "papel": f.get("papel", "lawyer"),
                "escritorio": f.get("escritorio"),
                "area": f.get("area"),
                "nome": f.get("nome")
            }
    return None

def filtrar_processos_por_permissao(processos, papel, escritorio=None, area=None):
    if papel == "owner":
        return processos
    elif papel == "manager":
        return [p for p in processos if p.get("escritorio") == escritorio]
    elif papel == "lawyer":
        return [p for p in processos if p.get("escritorio") == escritorio and p.get("area") == area]
    return []
# -------------------- Parte 4: Dashboard com Escalas de Cor e Consulta Manual --------------------
def calcular_status_processo(data_prazo, houve_movimentacao):
    hoje = datetime.date.today()
    dias_restantes = (data_prazo - hoje).days
    if houve_movimentacao:
        return "🔵"
    elif dias_restantes < 0:
        return "🔴"
    elif dias_restantes <= 10:
        return "🟡"
    else:
        return "🟢"

def consultar_movimentacoes_simples(numero_processo):
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={numero_processo}"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    andamentos = soup.find_all("tr", class_="fundocinza1")
    return [a.get_text(strip=True) for a in andamentos[:5]] if andamentos else ["Nenhuma movimentação encontrada"]

def mostrar_dashboard(processos):
    st.subheader("📋 Processos em Andamento")
    if not processos:
        st.info("Nenhum processo encontrado para exibir.")
        return

    for proc in processos:
        data_prazo = datetime.date.fromisoformat(proc.get("prazo", datetime.date.today().isoformat()))
        movimentacao = proc.get("houve_movimentacao", False)
        status = calcular_status_processo(data_prazo, movimentacao)

        with st.expander(f"{status} Processo: {proc['numero']}"):
            st.markdown(f"**Cliente:** {proc['cliente']}")
            st.markdown(f"**Descrição:** {proc['descricao']}")
            st.markdown(f"**Área:** {proc['area']}")
            st.markdown(f"**Prazo:** {data_prazo.strftime('%d/%m/%Y')}")
            st.markdown(f"**Valor Total:** R$ {proc['valor_total']:.2f}")
            st.markdown(f"**Responsável:** {proc['responsavel']}")

            if st.button(f"🔍 Consultar movimentações ({proc['numero']})"):
                with st.spinner("Consultando movimentações..."):
                    movimentacoes = consultar_movimentacoes_simples(proc['numero'])
                    st.success("Movimentações recentes:")
                    for mov in movimentacoes:
                        st.markdown(f"- {mov}")

# -------------------- Parte 5: Cadastro e Unificação de Escritórios + Administrador --------------------
def cadastrar_escritorio():
    st.subheader("🏢 Cadastro e Gerenciamento de Escritórios")

    with st.form("form_escritorio"):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome do Escritório*")
            cnpj = st.text_input("CNPJ*")
            endereco = st.text_input("Endereço*")
            telefone = st.text_input("Telefone*")
            email = st.text_input("Email*")
        with col2:
            responsavel_tecnico = st.text_input("Responsável Técnico*")
            email_tecnico = st.text_input("Email Técnico*")
            telefone_tecnico = st.text_input("Telefone Técnico*")
            area_atuacao = st.multiselect("Áreas de Atuação", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])

        st.markdown("### Dados do Administrador do Escritório")
        adm_usuario = st.text_input("Usuário Administrador*")
        adm_senha = st.text_input("Senha*")

        if st.form_submit_button("Salvar Escritório e Administrador"):
            campos_obrigatorios = [nome, cnpj, endereco, telefone, email, responsavel_tecnico, email_tecnico, telefone_tecnico, adm_usuario, adm_senha]
            if not all(campos_obrigatorios):
                st.warning("Preencha todos os campos obrigatórios marcados com *")
            else:
                dados_escritorio = {
                    "nome": nome,
                    "cnpj": cnpj,
                    "endereco": endereco,
                    "telefone": telefone,
                    "email": email,
                    "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "responsavel": st.session_state.get("usuario", "sistema"),
                    "responsavel_tecnico": responsavel_tecnico,
                    "telefone_tecnico": telefone_tecnico,
                    "email_tecnico": email_tecnico,
                    "area_atuacao": ", ".join(area_atuacao)
                }
                dados_admin = {
                    "tipo": "Funcionarios",
                    "nome": responsavel_tecnico,
                    "usuario": adm_usuario,
                    "senha": adm_senha,
                    "papel": "manager",
                    "escritorio": nome,
                    "area": ", ".join(area_atuacao)
                }
                ok1 = enviar_dados_para_planilha("Escritorio", dados_escritorio)
                ok2 = enviar_dados_para_planilha("Funcionarios", dados_admin)
                if ok1 and ok2:
                    st.success("Escritório e administrador cadastrados com sucesso!")


# -------------------- Parte 6: Cadastro de Funcionários com Limitação por Área --------------------
def cadastrar_funcionario(escritorios):
    st.subheader("👤 Cadastro de Funcionários")

    with st.form("form_funcionario"):
        nome = st.text_input("Nome Completo*")
        usuario = st.text_input("Usuário de Acesso*")
        senha = st.text_input("Senha de Acesso*")
        escritorio = st.selectbox("Escritório*", [e["nome"] for e in escritorios])
        papel = st.selectbox("Função no Sistema*", ["lawyer", "manager"])
        areas = st.multiselect("Áreas de Acesso Permitidas*", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])

        if st.form_submit_button("Salvar Funcionário"):
            if not nome or not usuario or not senha or not escritorio or not areas:
                st.warning("Preencha todos os campos obrigatórios!")
            else:
                dados = {
                    "tipo": "Funcionarios",
                    "nome": nome,
                    "usuario": usuario,
                    "senha": senha,
                    "papel": papel,
                    "escritorio": escritorio,
                    "area": ", ".join(areas)
                }
                if enviar_dados_para_planilha("Funcionarios", dados):
                    st.success("Funcionário cadastrado com sucesso!")

# -------------------- Parte 7: Relatórios com Restrições por Papel --------------------
def gerar_relatorios(processos, papel, escritorio=None, area=None):
    st.subheader("📊 Relatórios de Processos")

    filtros = {}
    if papel == "manager":
        filtros["escritorio"] = escritorio
    elif papel == "lawyer":
        filtros["escritorio"] = escritorio
        filtros["area"] = area

    processos_filtrados = [p for p in processos if
        (not filtros.get("escritorio") or p.get("escritorio") == filtros["escritorio"]) and
        (not filtros.get("area") or p.get("area") == filtros["area"])]

    if not processos_filtrados:
        st.info("Nenhum processo encontrado com os filtros de acesso.")
        return

    st.markdown(f"**Total de processos:** {len(processos_filtrados)}")
    df = pd.DataFrame(processos_filtrados)
    st.dataframe(df)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Exportar para PDF"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt="Relatório de Processos", ln=1, align='C')
            pdf.ln(10)
            for index, row in df.iterrows():
                linha = f"{row['numero']} - {row['cliente']} ({row['area']})"
                pdf.cell(200, 10, txt=linha, ln=1)
            nome_pdf = "relatorio_processos.pdf"
            pdf.output(nome_pdf)
            with open(nome_pdf, "rb") as f:
                st.download_button("Download PDF", f, file_name=nome_pdf)
    with col2:
        if st.button("📝 Exportar para DOCX"):
            doc = Document()
            doc.add_heading("Relatório de Processos", 0)
            for index, row in df.iterrows():
                doc.add_paragraph(f"Processo {row['numero']} - Cliente: {row['cliente']} - Área: {row['area']}")
            nome_docx = "relatorio_processos.docx"
            doc.save(nome_docx)
            with open(nome_docx, "rb") as f:
                st.download_button("Download DOCX", f, file_name=nome_docx)

# -------------------- Parte 8: Integração no Menu Principal --------------------
def main():
    st.title("⚖️ Sistema Jurídico Inteligente")
    dados = carregar_dados_globais()

    with st.sidebar:
        st.header("🔐 Login")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = login(usuario, senha, dados["FUNCIONARIOS"])
            if user:
                st.session_state.usuario = usuario
                st.session_state.papel = user["papel"]
                st.session_state.escritorio = user.get("escritorio")
                st.session_state.area = user.get("area")
                st.experimental_rerun()
                return
            else:
                st.error("Usuário ou senha inválidos")

    if "usuario" in st.session_state:
        papel = st.session_state.papel
        escritorio = st.session_state.get("escritorio")
        area = st.session_state.get("area")

        menu = ["Dashboard", "Relatórios"]
        if papel == "owner":
            menu += ["Cadastrar Escritório", "Cadastrar Funcionário"]
        elif papel == "manager":
            menu += ["Cadastrar Funcionário"]

        escolha = st.sidebar.radio("Navegação", menu)

        if escolha == "Dashboard":
            processos_filtrados = filtrar_processos_por_permissao(
                dados["PROCESSOS"], papel, escritorio, area
            )
            mostrar_dashboard(processos_filtrados)

        elif escolha == "Relatórios":
            gerar_relatorios(dados["PROCESSOS"], papel, escritorio, area)

        elif escolha == "Cadastrar Escritório" and papel == "owner":
            cadastrar_escritorio()

        elif escolha == "Cadastrar Funcionário" and papel in ["owner", "manager"]:
            cadastrar_funcionario(dados["ESCRITORIOS"])

if __name__ == '__main__':
    main()


