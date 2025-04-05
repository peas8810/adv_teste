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

CLIENTES = []
PROCESSOS = []

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
        opcoes = ["Dashboard", "Clientes", "Processos", "Petição IA"]
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

        elif escolha == "Clientes":
            st.subheader("👥 Cadastro de Clientes")
            nome = st.text_input("Nome do Cliente")
            email = st.text_input("Email")
            telefone = st.text_input("Telefone")
            aniversario = st.date_input("Data de Nascimento")
            if st.button("Salvar Cliente"):
                CLIENTES.append({
                    "nome": nome,
                    "email": email,
                    "telefone": telefone,
                    "aniversario": aniversario.strftime("%Y-%m-%d")
                })
                st.success("Cliente cadastrado com sucesso!")

        elif escolha == "Processos":
            st.subheader("📄 Cadastro de Processo")
            cliente_nome = st.text_input("Nome do Cliente Vinculado")
            numero_processo = st.text_input("Número do Processo")
            tipo_contrato = st.selectbox("Tipo de Contrato", ["Fixo", "Por Ato"])
            descricao = st.text_area("Descrição do Processo")
            valor_total = st.number_input("Valor Total do Processo", min_value=0.0, format="%.2f")
            valor_movimentado = st.number_input("Valor Movimentado", min_value=0.0, format="%.2f")
            if st.button("Salvar Processo"):
                PROCESSOS.append({
                    "cliente": cliente_nome,
                    "numero": numero_processo,
                    "tipo": tipo_contrato,
                    "descricao": descricao,
                    "valor_total": valor_total,
                    "valor_movimentado": valor_movimentado
                })
                st.success("Processo cadastrado com sucesso!")

            st.subheader("🔍 Consultar Processo via API TJ")
            processo = st.text_input("Número do Processo para Consulta")
            tribunal = st.selectbox("Tribunal", ["TJMG", "TJSP", "TJBA", "TJRJ"])
            if st.button("Consultar Andamentos"):
                st.info(f"(Simulado) Buscando movimentações no {tribunal} para o processo {processo}...")
                st.code("Andamento 1\nAndamento 2\nAndamento 3")

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
