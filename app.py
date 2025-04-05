import streamlit as st
import requests
import datetime
import json

# ---------------------------
# Funções de Autenticação e Acesso
# ---------------------------
def login(username, password):
    # TODO: Implementar validação contra banco de dados ou serviço de autenticação
    return True

def get_user_role(username):
    # Exemplo de papéis: 'owner', 'manager' e 'lawyer'
    if username.lower() == "dono":
        return "owner"
    elif username.lower() == "gestor":
        return "manager"
    else:
        return "lawyer"

# ---------------------------
# Integração com API dos Tribunais de Justiça (TJMG, TJSP, TJBA, TJRJ)
# ---------------------------
def get_process_movements(process_number, tribunal):
    # Exemplo: simula a chamada a uma API do TJ
    # Na implementação real, utilize requests.get/post com os endpoints e parâmetros necessários
    url_api = f"https://api.{tribunal.lower()}.gov.br/processos/{process_number}/movimentacoes"
    # Exemplo de chamada:
    # response = requests.get(url_api, headers={"Authorization": "SEU_TOKEN"})
    # return response.json()
    return {"movimentacoes": ["Andamento 1", "Andamento 2", "Andamento 3"]}

# ---------------------------
# Integração com Mercado Pago
# ---------------------------
def check_payment_status(user_id):
    # Exemplo: simula a verificação de status do pagamento via API do Mercado Pago
    # Na implementação real, faça uma chamada à API com os parâmetros corretos
    return {"status": "active", "dias_para_vencimento": 10}

def send_payment_alert(user_id):
    # Exemplo: envia alerta se o acesso estiver próximo do vencimento
    st.warning("Atenção: Seu acesso está próximo de vencer. Regularize o pagamento para não ter seu acesso bloqueado.")

# ---------------------------
# Integração com Google Drive via Apps Script
# ---------------------------
def save_data_to_google_drive(data, sheet_name):
    # URL do seu Apps Script que interage com o Google Drive/Sheets
    apps_script_url = "https://script.google.com/macros/s/SEU_APPS_SCRIPT_URL/exec"
    try:
        response = requests.post(apps_script_url, json={"sheet": sheet_name, "data": data})
        return response.status_code
    except Exception as e:
        st.error(f"Erro ao salvar dados: {e}")
        return None

# ---------------------------
# Aviso de Aniversário de Clientes
# ---------------------------
def check_birthdays(client_list):
    today = datetime.date.today()
    alerts = []
    for client in client_list:
        # Supondo que cada cliente seja um dicionário com 'nome' e 'aniversario' (formato "YYYY-MM-DD")
        birthday = datetime.datetime.strptime(client["aniversario"], "%Y-%m-%d").date()
        if birthday.month == today.month and birthday.day == today.day:
            alerts.append(f"Feliz aniversário, {client['nome']}!")
    return alerts

# ---------------------------
# Integração com IA Generativa para Criação de Petições
# ---------------------------
def create_petition(prompt):
    # Exemplo: simula chamada a uma API de IA (como OpenAI) para gerar petições
    # Na implementação real, use a biblioteca da API (ex: openai.ChatCompletion.create)
    return "Petição gerada com base no comando: " + prompt

# ---------------------------
# Controle Financeiro de Processos
# ---------------------------
def record_financial_data(process_id, total_value, movement_value):
    # Prepara os dados para serem enviados para o Google Drive/Sheets
    data = {
        "process_id": process_id,
        "valor_total": total_value,
        "valor_movimentacao": movement_value,
        "data": datetime.date.today().isoformat()
    }
    status = save_data_to_google_drive(data, "Financeiro")
    return status

# ---------------------------
# Função Principal do Sistema com Streamlit
# ---------------------------
def main():
    st.title("Sistema Escritório de Advocacia")

    # Área de Login
    st.sidebar.header("Login")
    username = st.sidebar.text_input("Usuário")
    password = st.sidebar.text_input("Senha", type="password")
    
    if st.sidebar.button("Entrar"):
        if login(username, password):
            role = get_user_role(username)
            st.sidebar.success(f"Logado como {role.upper()}")
            
            # Verifica status de pagamento
            payment_info = check_payment_status(username)
            if payment_info["status"] != "active":
                send_payment_alert(username)
            
            # Define menu de navegação baseado no papel do usuário
            if role == "owner":
                menu_options = ["Dashboard", "Gerenciar Escritórios", "Configurações"]
            elif role == "manager":
                menu_options = ["Dashboard", "Cadastro de Advogados", "Processos", "Financeiro"]
            else:
                menu_options = ["Dashboard", "Processos"]
            
            choice = st.sidebar.selectbox("Menu", menu_options)
            
            # ---------------------------
            # Dashboard: Exibe avisos e funções gerais
            # ---------------------------
            if choice == "Dashboard":
                st.header("Dashboard")
                
                # Aviso de Aniversários
                client_list = [
                    {"nome": "Cliente 1", "aniversario": "1990-04-05"},
                    {"nome": "Cliente 2", "aniversario": "1985-12-25"}
                ]
                birthday_alerts = check_birthdays(client_list)
                for alert in birthday_alerts:
                    st.info(alert)
                
                # Seção para criação de petições com IA generativa
                st.subheader("Gerar Petição")
                prompt = st.text_area("Descreva o comando para a petição")
                if st.button("Gerar Petição"):
                    petition = create_petition(prompt)
                    st.write(petition)
            
            # ---------------------------
            # Processos: Importação de movimentações e controle financeiro
            # ---------------------------
            if choice == "Processos":
                st.header("Gestão de Processos")
                process_number = st.text_input("Número do Processo")
                tribunal = st.selectbox("Selecione o Tribunal", ["TJMG", "TJSP", "TJBA", "TJRJ"])
                if st.button("Importar Movimentações"):
                    movements = get_process_movements(process_number, tribunal)
                    st.write("Movimentações importadas:", movements)
                
                st.subheader("Cadastro e Controle Financeiro")
                process_id = st.text_input("ID do Processo")
                total_value = st.number_input("Valor Total", min_value=0.0, format="%.2f")
                movement_value = st.number_input("Valor da Movimentação", min_value=0.0, format="%.2f")
                if st.button("Salvar Dados Financeiros"):
                    status = record_financial_data(process_id, total_value, movement_value)
                    if status == 200:
                        st.success("Dados financeiros salvos com sucesso!")
                    else:
                        st.error("Falha ao salvar os dados financeiros.")
            
            # ---------------------------
            # Cadastro de Advogados (para gestores)
            # ---------------------------
            if choice == "Cadastro de Advogados" and role == "manager":
                st.header("Cadastro de Advogados")
                lawyer_name = st.text_input("Nome do Advogado")
                lawyer_email = st.text_input("Email")
                if st.button("Cadastrar Advogado"):
                    # TODO: Implementar lógica de cadastro, possivelmente salvando os dados em uma planilha no Google Drive
                    st.success(f"Advogado {lawyer_name} cadastrado com sucesso!")
            
            # ---------------------------
            # Gerenciamento de Escritórios e Configurações (para o dono do sistema)
            # ---------------------------
            if choice == "Gerenciar Escritórios" and role == "owner":
                st.header("Gerenciamento de Escritórios")
                st.write("Funcionalidades para gerenciamento de escritórios serão implementadas aqui.")
            
            if choice == "Configurações" and role == "owner":
                st.header("Configurações do Sistema")
                st.write("Opções de configuração e personalização do sistema.")
        else:
            st.sidebar.error("Usuário ou senha inválidos.")

if __name__ == "__main__":
    main()
