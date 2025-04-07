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

def exibir_peticoes_ia():
    st.subheader("🤖 Gerador de Petições com IA")
    cliente = st.text_input("Nome do Cliente")
    prompt = st.text_area("Descreva sua necessidade jurídica")
    if st.button("Gerar Petição") and prompt and cliente:
        resposta = gerar_peticao_ia(prompt, cliente)
        st.text_area("Petição Gerada", resposta, height=300)

        nome_pdf = f"peticao_{cliente.replace(' ', '_')}.pdf"
        nome_docx = f"peticao_{cliente.replace(' ', '_')}.docx"

        col1, col2 = st.columns(2)
        with col1:
            if st.download_button("📄 Baixar PDF", data=open(exportar_peticao_pdf(nome_pdf, resposta), "rb").read(), file_name=nome_pdf):
                st.success("PDF exportado!")
        with col2:
            if st.download_button("📝 Baixar DOCX", data=open(exportar_peticao_docx(nome_docx, resposta), "rb").read(), file_name=nome_docx):
                st.success("DOCX exportado!")

def gerar_peticao_ia(prompt, cliente):
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
        if "choices" in resposta_json and resposta_json["choices"]:
            conteudo = resposta_json['choices'][0]['message']['content']
            HISTORICO_PETICOES.append({"cliente": cliente, "conteudo": conteudo, "prompt": prompt, "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
            return conteudo
        elif "error" in resposta_json:
            return f"❌ Erro do DeepSeek: {resposta_json['error']['message']}"
        else:
            return f"❌ Resposta inesperada da API: {resposta_json}"
    except Exception as e:
        return f"❌ Erro ao gerar petição: {e}"

def exportar_peticao_pdf(nome_arquivo, conteudo):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    for linha in conteudo.split('\n'):
        pdf.multi_cell(0, 10, linha)
    pdf.output(nome_arquivo)
    return nome_arquivo

def exportar_peticao_docx(nome_arquivo, conteudo):
    doc = Document()
    for linha in conteudo.split("\n"):
        doc.add_paragraph(linha)
    doc.save(nome_arquivo)
    return nome_arquivo
