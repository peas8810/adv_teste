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

        opcoes = ["Dashboard", "Clientes", "Processos", "Petições IA"]
        if papel == "owner":
            opcoes.append("Cadastrar Escritórios")
        elif papel == "manager":
            opcoes.append("Cadastrar Funcionários")

        escolha = st.sidebar.selectbox("Menu", opcoes)

        if escolha == "Dashboard":
            st.subheader("📋 Processos em Andamento")
            processos_visiveis = [p for p in PROCESSOS if papel == "owner" or
                                  (papel == "manager" and p["escritorio"] == st.session_state.dados_usuario["escritorio"]) or
                                  (papel == "lawyer" and p["escritorio"] == st.session_state.dados_usuario["escritorio"] and
                                   p["area"] == st.session_state.dados_usuario["area"])]
            for proc in processos_visiveis:
                status = calcular_status_processo(proc.get("prazo"), proc.get("houve_movimentacao", False))
                st.markdown(f"{status} **{proc['numero']}** - {proc['descricao']} (Cliente: {proc['cliente']})")

        elif escolha == "Clientes":
            st.subheader("👥 Cadastro de Clientes")
            nome = st.text_input("Nome do Cliente")
            email = st.text_input("Email")
            telefone = st.text_input("Telefone")
            aniversario = st.date_input("Data de Nascimento")
            if st.button("Salvar Cliente"):
                cliente = {
                    "nome": nome,
                    "email": email,
                    "telefone": telefone,
                    "aniversio": aniversario.strftime("%Y-%m-%d")
                }
                CLIENTES.append(cliente)
                salvar_google_sheets({"tipo": "cliente", **cliente})

        elif escolha == "Processos":
            st.subheader("📄 Cadastro de Processo")
            cliente_nome = st.text_input("Nome do Cliente Vinculado")
            numero_processo = st.text_input("Número do Processo")
            tipo_contrato = st.selectbox("Tipo de Contrato", ["Fixo", "Por Ato"])
            descricao = st.text_area("Descrição do Processo")
            valor_total = st.number_input("Valor Total", min_value=0.0, format="%.2f")
            valor_movimentado = st.number_input("Valor Movimentado", min_value=0.0, format="%.2f")
            prazo = st.date_input("Prazo Final", value=datetime.date.today() + datetime.timedelta(days=30))
            houve_movimentacao = st.checkbox("Houve movimentação recente?")
            area = st.selectbox("Área", ["Cível", "Criminal", "Trabalhista", "Previdenciário"])
            if st.button("Salvar Processo"):
                processo = {
                    "cliente": cliente_nome,
                    "numero": numero_processo,
                    "tipo_contrato": tipo_contrato,
                    "descricao": descricao,
                    "valor_total": valor_total,
                    "valor_movimentado": valor_movimentado,
                    "prazo": prazo.strftime("%Y-%m-%d"),
                    "houve_movimentacao": houve_movimentacao,
                    "escritorio": st.session_state.dados_usuario.get("escritorio", "Global"),
                    "area": area
                }
                PROCESSOS.append(processo)
                salvar_google_sheets({"tipo": "processo", **processo})

            st.markdown("---")
            st.subheader("🔎 Consultar Andamentos (Simulado)")
            num_consulta = st.text_input("Nº do processo para consulta")
            if st.button("Consultar TJSP"):
                resultados = consultar_movimentacoes_simples(num_consulta)
                for r in resultados:
                    st.markdown(f"- {r}")

        elif escolha == "Petições IA":
            st.subheader("🤖 Gerador de Petições com IA")
            prompt = st.text_area("Descreva sua necessidade jurídica")
            if st.button("Gerar Petição"):
                resposta = gerar_peticao_ia(prompt)
                st.text_area("Petição Gerada", resposta, height=300)

        elif escolha == "Cadastrar Escritórios":
            st.subheader("🏢 Cadastro de Escritórios")
            nome_esc = st.text_input("Nome do Escritório")
            usuario_esc = st.text_input("Usuário")
            senha_esc = st.text_input("Senha")
            if st.button("Cadastrar Escritório"):
                USERS[usuario_esc] = {"senha": senha_esc, "papel": "manager", "escritorio": nome_esc}
                st.success("Escritório cadastrado com sucesso!")

        elif escolha == "Cadastrar Funcionários":
            st.subheader("👩‍⚖️ Cadastro de Funcionários")
            nome_func = st.text_input("Nome")
            usuario_func = st.text_input("Usuário")
            senha_func = st.text_input("Senha")
            area_func = st.selectbox("Área", ["Cível", "Criminal", "Trabalhista", "Previdenciário"])
            if st.button("Cadastrar Funcionário"):
                USERS[usuario_func] = {
                    "senha": senha_func,
                    "papel": "lawyer",
                    "escritorio": st.session_state.dados_usuario["escritorio"],
                    "area": area_func
                }
                st.success("Funcionário cadastrado com sucesso!")

if __name__ == '__main__':
    main()
