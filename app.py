# Estrutura inicial do sistema jurídico em Streamlit com funcionalidades solicitadas

# -------------------- main.py --------------------
import streamlit as st
import datetime
import requests

# -------------------- Dados simulados --------------------
USERS = {
    "dono": {"senha": "dono123", "papel": "owner"},
    "gestor1": {"senha": "gestor123", "papel": "manager"},
    "adv1": {"senha": "adv123", "papel": "lawyer"},
}

# -------------------- Funções de Login --------------------
def login(usuario, senha):
    user = USERS.get(usuario)
    return user if user and user["senha"] == senha else None

def get_user_role(usuario):
    return USERS[usuario]["papel"]

# -------------------- Função principal --------------------
def main():
    st.set_page_config(page_title="Sistema Jurídico", layout="wide")
    st.title("Sistema Jurídico com IA, API dos TJs e Controle Financeiro")

    with st.sidebar:
        st.header("Login")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = login(usuario, senha)
            if user:
                st.session_state.usuario = usuario
                st.session_state.papel = user["papel"]
            else:
                st.error("Usuário ou senha incorretos")

    if "usuario" in st.session_state:
        papel = st.session_state.papel
        st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")
        opcoes = ["Dashboard", "Processos", "Petição IA"]
        if papel == "owner":
            opcoes.append("Gerenciar Escritórios")
        elif papel == "manager":
            opcoes.append("Cadastrar Advogados")

        escolha = st.sidebar.selectbox("Menu", opcoes)

        if escolha == "Dashboard":
            st.subheader("🎂 Avisos de Aniversário")
            aniversarios = [
                {"nome": "Ana Paula", "aniversario": "1990-04-05"},
                {"nome": "Carlos Silva", "aniversario": "1985-12-25"},
            ]
            hoje = datetime.date.today()
            for cliente in aniversarios:
                nasc = datetime.datetime.strptime(cliente["aniversario"], "%Y-%m-%d").date()
                if nasc.month == hoje.month and nasc.day == hoje.day:
                    st.success(f"Hoje é aniversário de {cliente['nome']} 🎉")

        elif escolha == "Processos":
            st.subheader("🔍 Consultar Processo via API TJ")
            processo = st.text_input("Número do Processo")
            tribunal = st.selectbox("Tribunal", ["TJMG", "TJSP", "TJBA", "TJRJ"])
            if st.button("Consultar Andamentos"):
                st.info(f"(Simulado) Buscando movimentações no {tribunal} para o processo {processo}...")
                st.code("Andamento 1\nAndamento 2\nAndamento 3")

            st.subheader("💰 Controle Financeiro do Processo")
            valor_total = st.number_input("Valor Total do Processo", min_value=0.0, format="%.2f")
            movimentado = st.number_input("Valor Movimentado", min_value=0.0, format="%.2f")
            if st.button("Salvar Financeiro"):
                st.success("Dados financeiros salvos no Google Drive (simulado).")

        elif escolha == "Petição IA":
            st.subheader("🤖 Gerar Petição com IA")
            comando = st.text_area("Digite o comando para a petição")
            if st.button("Gerar Petição"):
                texto_peticao = f"Petição gerada com base no comando: {comando}"
                st.text_area("Petição", texto_peticao, height=300)

        elif escolha == "Gerenciar Escritórios":
            st.subheader("🏢 Gestão de Escritórios")
            st.text_input("Nome do Escritório")
            st.button("Cadastrar Escritório")

        elif escolha == "Cadastrar Advogados":
            st.subheader("👩‍⚖️ Cadastro de Advogado")
            nome = st.text_input("Nome")
            email = st.text_input("Email")
            st.button("Cadastrar")

if __name__ == '__main__':
    main()
