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
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -------------------- Configurações --------------------
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configuração da API DeepSeek
DEEPSEEK_API_KEY = "sk-4cd98d6c538f42f68bd820a6f3cc44c9"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"

# Configuração do Google Sheets
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
SPREADSHEET_NAME = "SistemaJuridico"

# Dados do sistema
HISTORICO_PETICOES = []
USERS = {
    "dono": {"senha": "dono123", "papel": "owner"},
    "gestor1": {"senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A"},
    "adv1": {"senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Cível"},
}

# -------------------- Funções do Google Sheets --------------------
def conectar_google_sheets():
    """Conecta ao Google Sheets e retorna a planilha"""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(GOOGLE_SHEETS_CREDENTIALS), scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SPREADSHEET_NAME)
        return spreadsheet
    except Exception as e:
        st.error(f"Erro ao conectar ao Google Sheets: {e}")
        return None

def salvar_dados(sheet_name, dados):
    """Salva dados em uma aba específica da planilha"""
    try:
        spreadsheet = conectar_google_sheets()
        if spreadsheet:
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except:
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="20")
            
            # Verifica se é uma nova linha ou atualização
            if isinstance(dados, dict):
                headers = worksheet.row_values(1)
                if not headers:
                    worksheet.append_row(list(dados.keys()))
                worksheet.append_row(list(dados.values()))
            elif isinstance(dados, list):
                worksheet.append_rows(dados)
            
            st.success(f"Dados salvos com sucesso na aba {sheet_name}!")
    except Exception as e:
        st.error(f"Erro ao salvar dados: {e}")

def carregar_dados(sheet_name):
    """Carrega dados de uma aba específica"""
    try:
        spreadsheet = conectar_google_sheets()
        if spreadsheet:
            worksheet = spreadsheet.worksheet(sheet_name)
            return worksheet.get_all_records()
    except Exception as e:
        st.warning(f"Nenhum dado encontrado na aba {sheet_name}")
    return []

# -------------------- Funções do Sistema --------------------
def login(usuario, senha):
    """Autentica usuário no sistema"""
    user = USERS.get(usuario)
    return user if user and user["senha"] == senha else None

def calcular_status_processo(data_prazo, houve_movimentacao):
    """Calcula o status do processo com base no prazo"""
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
    """Consulta movimentações processuais simuladas"""
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={numero_processo}"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    andamentos = soup.find_all("tr", class_="fundocinza1")
    return [a.get_text(strip=True) for a in andamentos[:5]] if andamentos else ["Nenhuma movimentação encontrada"]

def gerar_peticao_ia(prompt, temperatura=0.7, max_tokens=2000, tentativas=3):
    """Gera petição com tratamento robusto de timeout e retry"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "Você é um assistente jurídico especializado. Responda com linguagem técnica formal."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": temperatura,
        "max_tokens": max_tokens
    }
    
    for tentativa in range(tentativas):
        try:
            start_time = time.time()
            
            with httpx.Client(timeout=25) as client:
                response = client.post(
                    DEEPSEEK_ENDPOINT,
                    headers=headers,
                    json=payload
                )
            
            response_time = time.time() - start_time
            st.sidebar.metric("Tempo de resposta API", f"{response_time:.2f}s")
            
            response.raise_for_status()
            resposta_json = response.json()
            
            if not resposta_json.get('choices'):
                raise ValueError("Resposta da API incompleta")
                
            return resposta_json['choices'][0]['message']['content']
            
        except httpx.ReadTimeout:
            if tentativa < tentativas - 1:
                st.warning(f"Tentativa {tentativa + 1} falhou (timeout). Tentando novamente...")
                continue
            else:
                raise Exception("O servidor demorou muito para responder após várias tentativas")
                
        except httpx.HTTPStatusError as e:
            error_msg = f"Erro HTTP {e.response.status_code}"
            if e.response.status_code == 402:
                error_msg += " - Saldo insuficiente na API"
            raise Exception(f"{error_msg}: {e.response.text}")
            
        except Exception as e:
            if tentativa == tentativas - 1:
                raise Exception(f"Erro na requisição: {str(e)}")
            continue
    
    return "❌ Falha ao gerar petição após múltiplas tentativas"

# ... (mantenha as funções exportar_pdf, exportar_docx, gerar_relatorio_pdf e aplicar_filtros como estão) ...

# -------------------- Interface Principal --------------------
def main():
    st.title("Sistema Jurídico com DeepSeek AI")

    # Carrega dados do Google Sheets
    CLIENTES = carregar_dados("Clientes") or []
    PROCESSOS = carregar_dados("Processos") or []
    ESCRITORIOS = carregar_dados("Escritorios") or []

    # Sidebar - Login
    with st.sidebar:
        st.header("🔐 Login")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        
        if st.button("Entrar"):
            user = login(usuario, senha)
            if user:
                st.session_state.usuario = usuario
                st.session_state.papel = user["papel"]
                st.session_state.dados_usuario = user
                st.success("Login realizado com sucesso!")
            else:
                st.error("Credenciais inválidas")

    # Conteúdo principal após login
    if "usuario" in st.session_state:
        papel = st.session_state.papel
        st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")

        # Menu principal
        opcoes = ["Dashboard", "Clientes", "Processos", "Petições IA", "Histórico", "Relatórios"]
        if papel == "owner":
            opcoes.extend(["Cadastrar Escritórios", "Gerenciar Escritórios"])
        elif papel == "manager":
            opcoes.append("Cadastrar Funcionários")

        escolha = st.sidebar.selectbox("Menu", opcoes)

        # Dashboard
        if escolha == "Dashboard":
            st.subheader("📋 Processos em Andamento")
            processos_visiveis = [p for p in PROCESSOS if papel == "owner" or
                                (papel == "manager" and p["escritorio"] == st.session_state.dados_usuario["escritorio"]) or
                                (papel == "lawyer" and p["escritorio"] == st.session_state.dados_usuario["escritorio"] and
                                p["area"] == st.session_state.dados_usuario["area"])]
            
            if processos_visiveis:
                for proc in processos_visiveis:
                    prazo_default = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%Y-%m-%d") 
                    data_prazo_str = proc.get("prazo", prazo_default)
                    data_prazo = datetime.date.fromisoformat(data_prazo_str)
                    movimentacao = proc.get("houve_movimentacao", False)
                    status = calcular_status_processo(data_prazo, movimentacao)
                    
                    with st.expander(f"{status} Processo: {proc['numero']}"):
                        st.write(f"**Cliente:** {proc['cliente']}")
                        st.write(f"**Descrição:** {proc['descricao']}")
                        st.write(f"**Área:** {proc['area']}")
                        st.write(f"**Prazo:** {data_prazo.strftime('%d/%m/%Y')}")
                        st.write(f"**Valor:** R$ {proc['valor_total']:,.2f}")
            else:
                st.info("Nenhum processo cadastrado.")

        # Clientes
        elif escolha == "Clientes":
            st.subheader("👥 Cadastro de Clientes")
            
            with st.form("form_cliente"):
                nome = st.text_input("Nome Completo*", key="nome_cliente")
                email = st.text_input("E-mail*")
                telefone = st.text_input("Telefone*")
                aniversario = st.date_input("Data de Nascimento")
                observacoes = st.text_area("Observações")
                
                if st.form_submit_button("Salvar Cliente"):
                    if not nome or not email or not telefone:
                        st.warning("Campos obrigatórios (*) não preenchidos!")
                    else:
                        novo_cliente = {
                            "nome": nome,
                            "email": email,
                            "telefone": telefone,
                            "aniversario": aniversario.strftime("%Y-%m-%d"),
                            "observacoes": observacoes,
                            "cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "responsavel": st.session_state.usuario
                        }
                        CLIENTES.append(novo_cliente)
                        salvar_dados("Clientes", novo_cliente)
                        st.success("Cliente cadastrado com sucesso!")

        # Processos
        elif escolha == "Processos":
            st.subheader("📄 Gestão de Processos")
            
            with st.form("form_processo"):
                cliente_nome = st.text_input("Cliente*")
                numero_processo = st.text_input("Número do Processo*")
                tipo_contrato = st.selectbox("Tipo de Contrato*", ["Fixo", "Por Ato", "Contingência"])
                descricao = st.text_area("Descrição do Caso*")
                
                col1, col2 = st.columns(2)
                with col1:
                    valor_total = st.number_input("Valor Total (R$)*", min_value=0.0, format="%.2f")
                with col2:
                    valor_movimentado = st.number_input("Valor Movimentado (R$)", min_value=0.0, format="%.2f")
                
                prazo = st.date_input("Prazo Final*", value=datetime.date.today() + datetime.timedelta(days=30))
                houve_movimentacao = st.checkbox("Houve movimentação recente?")
                area = st.selectbox("Área Jurídica*", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                
                if st.form_submit_button("Salvar Processo"):
                    if not cliente_nome or not numero_processo or not descricao:
                        st.warning("Campos obrigatórios (*) não preenchidos!")
                    else:
                        novo_processo = {
                            "cliente": cliente_nome,
                            "numero": numero_processo,
                            "tipo": tipo_contrato,
                            "descricao": descricao,
                            "valor_total": valor_total,
                            "valor_movimentado": valor_movimentado,
                            "prazo": prazo.strftime("%Y-%m-%d"),
                            "houve_movimentacao": houve_movimentacao,
                            "escritorio": st.session_state.dados_usuario.get("escritorio", "Global"),
                            "area": area,
                            "responsavel": st.session_state.usuario,
                            "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        PROCESSOS.append(novo_processo)
                        salvar_dados("Processos", novo_processo)
                        st.success("Processo cadastrado com sucesso!")

        # Gerenciar Escritórios
        elif escolha == "Gerenciar Escritórios" and papel == "owner":
            st.subheader("🏢 Gerenciar Escritórios")
            
            tab1, tab2 = st.tabs(["Cadastrar Escritório", "Lista de Escritórios"])
            
            with tab1:
                with st.form("form_escritorio"):
                    nome = st.text_input("Nome do Escritório*")
                    endereco = st.text_input("Endereço Completo*")
                    telefone = st.text_input("Telefone*")
                    email = st.text_input("E-mail*")
                    cnpj = st.text_input("CNPJ")
                    
                    if st.form_submit_button("Salvar Escritório"):
                        if not nome or not endereco or not telefone or not email:
                            st.warning("Campos obrigatórios (*) não preenchidos!")
                        else:
                            novo_escritorio = {
                                "nome": nome,
                                "endereco": endereco,
                                "telefone": telefone,
                                "email": email,
                                "cnpj": cnpj,
                                "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "responsavel": st.session_state.usuario
                            }
                            ESCRITORIOS.append(novo_escritorio)
                            salvar_dados("Escritorios", novo_escritorio)
                            st.success("Escritório cadastrado com sucesso!")
            
            with tab2:
                if ESCRITORIOS:
                    st.dataframe(ESCRITORIOS)
                else:
                    st.info("Nenhum escritório cadastrado ainda")

        # ... (mantenha as outras seções como Petições IA, Histórico, Relatórios, etc.)

if __name__ == '__main__':
    main()
