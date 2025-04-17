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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados_da_planilha(tipo):
    try:
        response = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo}, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Erro ao carregar dados ({tipo}): {e}")
        return []

def enviar_dados_para_planilha(tipo, dados):
    try:
        payload = {"tipo": tipo, **dados}
        response = httpx.post(GAS_WEB_APP_URL, json=payload, timeout=10)
        return response.text.strip() == "OK"
    except Exception as e:
        st.error(f"Erro ao enviar dados ({tipo}): {e}")
        return False

def get_dataframe_with_cols(data, columns):
    df = pd.DataFrame(data)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]

def exportar_pdf(texto, nome_arquivo="relatorio"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, texto)
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def main():
    st.title("Sistema Jurídico")

    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    LEADS = carregar_dados_da_planilha("Lead") or []

    escolha = st.sidebar.selectbox("Menu", ["Clientes", "Gestão de Leads", "Processos", "Gerenciar Funcionários"])

    if escolha == "Clientes":
        st.subheader("👥 Cadastro de Clientes")
        with st.form("form_cliente"):
            nome = st.text_input("Nome Completo*", key="nome_cliente")
            email = st.text_input("E-mail*")
            telefone = st.text_input("Telefone*")
            aniversario = st.date_input("Data de Nascimento")
            endereco = st.text_input("Endereço*", placeholder="Rua, número, bairro, cidade, CEP")
            escritorio = st.selectbox("Escritório", [e["nome"] for e in ESCRITORIOS] + ["Outro"])
            observacoes = st.text_area("Observações")
            if st.form_submit_button("Salvar Cliente"):
                if not nome or not email or not telefone or not endereco:
                    st.warning("Campos obrigatórios não preenchidos!")
                else:
                    novo_cliente = {
                        "nome": nome,
                        "email": email,
                        "telefone": telefone,
                        "aniversario": aniversario.strftime("%Y-%m-%d"),
                        "endereco": endereco,
                        "observacoes": observacoes,
                        "cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "responsavel": "sistema",
                        "escritorio": escritorio
                    }
                    if enviar_dados_para_planilha("Cliente", novo_cliente):
                        CLIENTES.append(novo_cliente)
                        st.success("Cliente cadastrado com sucesso!")
        st.subheader("Lista de Clientes")
        if CLIENTES:
            df_cliente = get_dataframe_with_cols(CLIENTES, ["nome", "email", "telefone", "endereco", "cadastro"])
            st.dataframe(df_cliente)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Exportar Clientes (TXT)"):
                    txt = "\n".join([
                        f"{c.get('nome', '')} | {c.get('email', '')} | {c.get('telefone', '')}"
                        for c in CLIENTES
                    ])
                    st.download_button("Baixar TXT", txt, file_name="clientes.txt")
            with col2:
                if st.button("Exportar Clientes (PDF)"):
                    texto_pdf = "\n".join([
                        f"{c.get('nome', '')} | {c.get('email', '')} | {c.get('telefone', '')}"
                        for c in CLIENTES
                    ])
                    pdf_file = exportar_pdf(texto_pdf, nome_arquivo="clientes")
                    with open(pdf_file, "rb") as f:
                        st.download_button("Baixar PDF", f, file_name=pdf_file)
        else:
            st.info("Nenhum cliente cadastrado.")

    elif escolha == "Gestão de Leads":
        st.subheader("📇 Gestão de Leads")
        with st.form("form_lead"):
            nome = st.text_input("Nome*", key="nome_lead")
            contato = st.text_input("Contato*")
            email = st.text_input("E-mail*")
            data_aniversario = st.date_input("Data de Aniversário")
            if st.form_submit_button("Salvar Lead"):
                if not nome or not contato or not email:
                    st.warning("Preencha todos os campos obrigatórios!")
                else:
                    novo_lead = {
                        "nome": nome,
                        "numero": contato,
                        "email": email,
                        "data_aniversario": data_aniversario.strftime("%Y-%m-%d"),
                        "origem": "lead",
                        "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    if enviar_dados_para_planilha("Lead", novo_lead):
                        LEADS.append(novo_lead)
                        st.success("Lead cadastrado com sucesso!")
        st.subheader("Lista de Leads")
        if LEADS:
            df_leads = get_dataframe_with_cols(LEADS, ["nome", "numero", "email", "data_aniversario", "origem", "data_cadastro"])
            st.dataframe(df_leads)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Exportar Leads (TXT)"):
                    txt = "\n".join([
                        f"{l.get('nome', '')} | {l.get('numero', '')} | {l.get('email', '')}"
                        for l in LEADS
                    ])
                    st.download_button("Baixar TXT", txt, file_name="leads.txt")
            with col2:
                if st.button("Exportar Leads (PDF)"):
                    texto_pdf = "\n".join([
                        f"{l.get('nome', '')} | {l.get('numero', '')} | {l.get('email', '')}"
                        for l in LEADS
                    ])
                    pdf_file = exportar_pdf(texto_pdf, nome_arquivo="leads")
                    with open(pdf_file, "rb") as f:
                        st.download_button("Baixar PDF", f, file_name=pdf_file)
        else:
            st.info("Nenhum lead cadastrado.")

    elif escolha == "Processos":
        st.subheader("📄 Cadastro de Processos")
        with st.form("form_processo"):
            cliente_nome = st.text_input("Cliente*")
            numero_processo = st.text_input("Número do Processo*")
            tipo_contrato = st.selectbox("Tipo de Contrato*", ["Fixo", "Por Ato", "Contingência"])
            descricao = st.text_area("Descrição do Caso*")
            prazo_inicial = st.date_input("Prazo Inicial*", value=datetime.date.today())
            prazo_final = st.date_input("Prazo Final*", value=datetime.date.today() + datetime.timedelta(days=30))
            houve_movimentacao = st.checkbox("Houve movimentação recente?")
            encerrado = st.checkbox("Processo Encerrado?")
            if st.form_submit_button("Salvar Processo"):
                if not cliente_nome or not numero_processo or not descricao:
                    st.warning("Campos obrigatórios (*) não preenchidos!")
                else:
                    novo_processo = {
                        "cliente": cliente_nome,
                        "numero": numero_processo,
                        "contrato": tipo_contrato,
                        "descricao": descricao,
                        "prazo_inicial": prazo_inicial.strftime("%Y-%m-%d"),
                        "prazo": prazo_final.strftime("%Y-%m-%d"),
                        "houve_movimentacao": houve_movimentacao,
                        "encerrado": encerrado,
                        "responsavel": "sistema",
                        "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    if enviar_dados_para_planilha("Processo", novo_processo):
                        PROCESSOS.append(novo_processo)
                        st.success("Processo cadastrado com sucesso!")
        st.subheader("Lista de Processos")
        if PROCESSOS:
            df_proc = get_dataframe_with_cols(PROCESSOS, ["numero", "cliente", "contrato", "prazo", "responsavel"])
            st.dataframe(df_proc)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Exportar Processos (TXT)"):
                    txt = "\n".join([
                        f"{p.get('cliente', '')} | {p.get('numero', '')} | {p.get('prazo', '')}"
                        for p in PROCESSOS
                    ])
                    st.download_button("Baixar TXT", txt, file_name="processos.txt")
            with col2:
                if st.button("Exportar Processos (PDF)"):
                    texto_pdf = "\n".join([
                        f"{p.get('cliente', '')} | {p.get('numero', '')} | {p.get('prazo', '')}"
                        for p in PROCESSOS
                    ])
                    pdf_file = exportar_pdf(texto_pdf, nome_arquivo="processos")
                    with open(pdf_file, "rb") as f:
                        st.download_button("Baixar PDF", f, file_name=pdf_file)
        else:
            st.info("Nenhum processo cadastrado.")

    elif escolha == "Gerenciar Funcionários":
        st.subheader("👥 Lista de Funcionários")
        if FUNCIONARIOS:
            df_func = get_dataframe_with_cols(FUNCIONARIOS, ["nome", "email", "telefone", "usuario", "papel", "escritorio", "area"])
            st.dataframe(df_func)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Exportar Funcionários (TXT)"):
                    txt = "\n".join([
                        f"{f.get('nome', '')} | {f.get('email', '')} | {f.get('telefone', '')}"
                        for f in FUNCIONARIOS
                    ])
                    st.download_button("Baixar TXT", txt, file_name="funcionarios.txt")
            with col2:
                if st.button("Exportar Funcionários (PDF)"):
                    texto_pdf = "\n".join([
                        f"{f.get('nome', '')} | {f.get('email', '')} | {f.get('telefone', '')}"
                        for f in FUNCIONARIOS
                    ])
                    pdf_file = exportar_pdf(texto_pdf, nome_arquivo="funcionarios")
                    with open(pdf_file, "rb") as f:
                        st.download_button("Baixar PDF", f, file_name=pdf_file)
        else:
            st.info("Nenhum funcionário cadastrado.")

if __name__ == '__main__':
    main()
