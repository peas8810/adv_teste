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

# ... (restante do código permanece igual até o final do arquivo atual)

# -------------------- APP principal --------------------
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

        opcoes = ["Dashboard", "Clientes", "Processos", "Petições IA", "Histórico de Petições"]
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
            exibir_peticoes_ia()

        elif escolha == "Histórico de Petições":
            st.subheader("📚 Histórico de Petições")
            if HISTORICO_PETICOES:
                for pet in reversed(HISTORICO_PETICOES):
                    with st.expander(f"{pet['data']} - {pet['cliente']}"):
                        st.markdown(f"**Prompt:** {pet['prompt']}")
                        st.text_area("Conteúdo da Petição", pet['conteudo'], height=200)
            else:
                st.info("Nenhuma petição gerada ainda.")

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
