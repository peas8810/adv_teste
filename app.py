# -------------------- app.py --------------------
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

# -------------------- Configurações externas --------------------
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-b6021a65e36340b999b3e6817e064d50")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"

HISTORICO_PETICOES = []
USERS = {
    "dono": {"senha": "dono123", "papel": "owner"},
    "gestor1": {"senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A"},
    "adv1": {"senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Cível"},
}
CLIENTES = []
PROCESSOS = []
GOOGLE_SHEETS_WEBHOOK = "https://script.google.com/macros/s/AKfycbytp0BA1x2PnjcFhunbgWEoMxZmCobyZHNzq3Mxabr41RScNAH-nYIlBd-OySWv5dcx/exec"

def login(usuario, senha):
    user = USERS.get(usuario)
    return user if user and user["senha"] == senha else None

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

def salvar_google_sheets(payload):
    try:
        response = requests.post(GOOGLE_SHEETS_WEBHOOK, json=payload)
        if response.status_code == 200:
            st.success("Dados enviados ao Google Sheets!")
        else:
            st.error("Erro ao salvar no Google Sheets.")
    except Exception as e:
        st.error(f"Erro na conexão com Google Sheets: {e}")

def consultar_movimentacoes_simples(numero_processo):
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={numero_processo}"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    andamentos = soup.find_all("tr", class_="fundocinza1")
    return [a.get_text(strip=True) for a in andamentos[:5]] if andamentos else ["Nenhuma movimentação encontrada"]

def gerar_peticao_ia(prompt):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Você é um advogado especialista em petições."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = httpx.post(DEEPSEEK_ENDPOINT, headers=headers, json=payload)
        resposta_json = response.json()
        return resposta_json['choices'][0]['message']['content']
    except Exception as e:
        return f"❌ Erro ao gerar petição: {e}"

def exportar_pdf(texto):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for linha in texto.split("\n"):
        pdf.multi_cell(0, 10, linha)
    pdf_path = "peticao_gerada.pdf"
    pdf.output(pdf_path)
    return pdf_path

def exportar_docx(texto):
    doc = Document()
    for linha in texto.split("\n"):
        doc.add_paragraph(linha)
    docx_path = "peticao_gerada.docx"
    doc.save(docx_path)
    return docx_path

def aplicar_filtros(dados, campos):
    filtrados = dados
    for campo in campos:
        if campo in dados[0]:
            if "data" in campo.lower():
                col1, col2 = st.columns(2)
                with col1:
                    data_inicio = st.date_input(f"Data inicial de {campo}", value=datetime.date(2000, 1, 1))
                with col2:
                    data_fim = st.date_input(f"Data final de {campo}", value=datetime.date.today())
                filtrados = [d for d in filtrados if campo in d and data_inicio <= datetime.date.fromisoformat(d[campo]) <= data_fim]
            else:
                valor = st.text_input(f"Filtrar por {campo.capitalize()} (deixe em branco para ignorar)")
                if valor:
                    filtrados = [d for d in filtrados if str(d.get(campo, '')).lower() == valor.lower()]
    return filtrados

def main():
    st.title("Sistema Jurídico com IA, Scraping e Google Sheets")

    with st.sidebar:
        st.header("Login")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = login(usuario, senha)
            if user:
                st.session_state.usuario = usuario
                st.session_state.papel = user["papel"]
                st.session_state.dados_usuario = user
            else:
                st.error("Usuário ou senha incorretos")

    if "usuario" in st.session_state:
        papel = st.session_state.papel
        st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")

        opcoes = ["Dashboard", "Clientes", "Processos", "Petições IA", "Histórico de Petições", "Relatórios"]
        if papel == "owner":
            opcoes.append("Cadastrar Escritórios")
        elif papel == "manager":
            opcoes.append("Cadastrar Funcionários")

        escolha = st.sidebar.selectbox("Menu", opcoes)

        if escolha == "Relatórios":
            st.subheader("📊 Emissão de Relatórios")
            tipo_relatorio = st.selectbox("Escolha o tipo de dado para emitir relatório", ["Clientes", "Processos", "Petições"])
            dados = []
            if tipo_relatorio == "Clientes":
                dados = CLIENTES
            elif tipo_relatorio == "Processos":
                dados = PROCESSOS
            elif tipo_relatorio == "Petições":
                dados = HISTORICO_PETICOES

            if dados:
                st.markdown("### 🔍 Filtros")
                campos = list(dados[0].keys())
                dados = aplicar_filtros(dados, campos)

            for item in dados:
                st.json(item)

            if dados:
                if st.button("Exportar para PDF"):
                    texto = "\n\n".join([json.dumps(d, indent=2, ensure_ascii=False) for d in dados])
                    caminho = exportar_pdf(texto)
                    st.success("Relatório exportado em PDF")
                    with open(caminho, "rb") as file:
                        st.download_button("📄 Baixar PDF", file, file_name=caminho)

                if st.button("Exportar para DOCX"):
                    texto = "\n\n".join([json.dumps(d, indent=2, ensure_ascii=False) for d in dados])
                    caminho = exportar_docx(texto)
                    st.success("Relatório exportado em DOCX")
                    with open(caminho, "rb") as file:
                        st.download_button("📄 Baixar DOCX", file, file_name=caminho)

if __name__ == '__main__':
    main()
