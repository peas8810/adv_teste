import streamlit as st
import datetime
import httpx
import requests
import json
import time
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

# Configurações Iniciais
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configurações de API e Google Apps Script
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-...")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# Dicionário de usuários
USERS = {
    "dono": {"senha": "dono123", "papel": "owner"},
    "gestor1": {"senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A"},
    "adv1": {"senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Cível"},
}

# -------------------- Funções Otimizadas --------------------

@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados_da_planilha(tipo, debug=False):
    """
    Carrega e retorna os dados da planilha para o tipo especificado. 
    Utiliza cache para evitar múltiplas requisições em um curto intervalo.
    """
    try:
        response = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo}, timeout=10)
        response.raise_for_status()
        if debug:
            st.text(f"🔍 URL chamada: {response.url}")
            st.text(f"📄 Resposta bruta: {response.text[:500]}")
        return response.json()
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados ({tipo}): {e}")
        return []


def enviar_dados_para_planilha(tipo, dados):
    """
    Envia os dados para o Google Sheets via Google Apps Script usando método POST.
    Retorna True se a resposta for "OK", caso contrário False.
    """
    try:
        payload = {"tipo": tipo, **dados}
        with httpx.Client(timeout=10) as client:
            response = client.post(GAS_WEB_APP_URL, json=payload)
        if response.text.strip() == "OK":
            return True
        else:
            st.error(f"❌ Erro no envio: {response.text}")
            return False
    except Exception as e:
        st.error(f"❌ Erro ao enviar dados ({tipo}): {e}")
        return False


def converter_prazo(prazo_str):
    """Converte uma string no formato ISO para objeto date."""
    if not prazo_str:
        return datetime.date.today()
    try:
        return datetime.date.fromisoformat(prazo_str)
    except ValueError:
        st.warning(f"Formato de data inválido: {prazo_str}. Utilizando data de hoje.")
        return datetime.date.today()


def login(usuario, senha):
    """Autentica o usuário com base no dicionário USERS."""
    user = USERS.get(usuario)
    return user if user and user["senha"] == senha else None


def calcular_status_processo(data_prazo, houve_movimentacao):
    """Calcula e retorna o status do processo conforme prazo e movimentação."""
    hoje = datetime.date.today()
    dias_restantes = (data_prazo - hoje).days
    if houve_movimentacao:
        return "🔵 Movimentado"
    elif dias_restantes < 0:
        return "🔴 Atrasado"
    elif dias_restantes <= 10:
        return "🟡 Atenção"
    else:
        return "🟢 Normal"


def consultar_movimentacoes_simples(numero_processo):
    """
    Consulta movimentações simuladas para o número do processo informado.
    """
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={numero_processo}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        andamentos = soup.find_all("tr", class_="fundocinza1")
        return [a.get_text(strip=True) for a in andamentos[:5]] if andamentos else ["Nenhuma movimentação encontrada"]
    except Exception:
        return ["Erro ao consultar movimentações"]


def gerar_peticao_ia(prompt, temperatura=0.7, max_tokens=2000, tentativas=3):
    """
    Gera uma petição utilizando a API DeepSeek com tratamento de tentativas e timeout.
    """
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
            {"role": "user", "content": prompt}
        ],
        "temperature": temperatura,
        "max_tokens": max_tokens
    }
    for tentativa in range(tentativas):
        try:
            start_time = time.time()
            with httpx.Client(timeout=30) as client:
                response = client.post(DEEPSEEK_ENDPOINT, headers=headers, json=payload)
            tempo_resposta = time.time() - start_time
            st.sidebar.metric("Tempo de resposta API", f"{tempo_resposta:.2f}s")
            response.raise_for_status()
            resposta_json = response.json()
            if not resposta_json.get('choices'):
                raise ValueError("Resposta incompleta")
            return resposta_json['choices'][0]['message']['content']
        except httpx.ReadTimeout:
            if tentativa < tentativas - 1:
                st.warning(f"Tentativa {tentativa + 1} falhou (timeout). Tentando novamente...")
                continue
            else:
                raise Exception("Servidor demorou muito para responder.")
        except Exception as e:
            if tentativa == tentativas - 1:
                raise Exception(f"Erro na requisição: {e}")
            continue
    return "❌ Falha ao gerar petição após múltiplas tentativas"


# Outras funções (exportação, filtros, etc.) permanecem com lógicas similares,
# mas podem também ser otimizadas com cache, se aplicável.

# -------------------- Interface Principal --------------------
def main():
    st.title("Sistema Jurídico com DeepSeek AI")
    
    # Carregar dados com cache para melhorar performance
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HISTORICO_PETICOES = carregar_dados_da_planilha("Historico_Peticao") or []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []
    
    # Sidebar: Login
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
    
    # Exibir conteúdo principal somente se o usuário estiver logado
    if "usuario" in st.session_state:
        # (A partir daqui, o restante da interface – dashboards, cadastros, consultas,
        # geração de petições, relatórios, etc. – permanece com a lógica original,
        # integrando as funções de envio e carregamento otimizadas.)
        st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({st.session_state.papel})")
        # ... (demais módulos do sistema)
        st.subheader("Exemplo: Cadastro de Cliente")
        with st.form("form_cliente"):
            nome = st.text_input("Nome Completo*")
            email = st.text_input("E-mail*")
            telefone = st.text_input("Telefone*")
            if st.form_submit_button("Salvar Cliente"):
                if nome and email and telefone:
                    novo_cliente = {
                        "nome": nome,
                        "email": email,
                        "telefone": telefone,
                        "cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "responsavel": st.session_state.usuario
                    }
                    if enviar_dados_para_planilha("Cliente", novo_cliente):
                        st.success("Cliente cadastrado e salvo na planilha!")
                else:
                    st.warning("Preencha os campos obrigatórios.")

if __name__ == '__main__':
    main()
