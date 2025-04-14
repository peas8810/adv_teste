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
from fpdf import FPDF
from docx import Document

# -------------------- Configurações Iniciais --------------------
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configuração da API DeepSeek e Google Apps Script
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-4cd98d6c538f42f68bd820a6f3cc44c9")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# Dados do sistema (Usuários)
USERS = {
    "dono": {"senha": "dono123", "papel": "owner"},
    "gestor1": {"senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A"},
    "adv1": {"senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Cível"},
}

# -------------------- Funções Auxiliares e Otimizadas --------------------

def converter_prazo(prazo_str):
    """
    Converte uma string no formato ISO ("YYYY-MM-DD") para um objeto date.
    Se o valor for nulo ou estiver em formato inválido, retorna a data de hoje.
    """
    if not prazo_str:
        return datetime.date.today()
    try:
        return datetime.date.fromisoformat(prazo_str)
    except ValueError:
        st.warning(f"Formato de data inválido: {prazo_str}. Utilizando a data de hoje.")
        return datetime.date.today()

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
    except json.JSONDecodeError:
        st.error(f"❌ Resposta inválida para o tipo '{tipo}'. O servidor não retornou JSON válido.")
        return []
    except Exception as e:
        st.warning(f"⚠️ Erro ao carregar dados ({tipo}): {e}")
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

def login(usuario, senha):
    """Autentica o usuário no sistema com base no dicionário USERS."""
    user = USERS.get(usuario)
    return user if user and user["senha"] == senha else None

def calcular_status_processo(data_prazo, houve_movimentacao):
    """
    Calcula o status do processo com base na data final e se houve movimentação.
    Retorna:
      - "🔵 Movimentado" se houve movimentação;
      - "🔴 Atrasado" se o prazo já passou;
      - "🟡 Atenção" se faltam 10 ou menos dias;
      - "🟢 Normal" caso contrário.
    """
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
    Consulta movimentações processuais simuladas para o número do processo informado.
    Retorna uma lista com até 5 movimentações ou uma mensagem caso não sejam encontradas.
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

def gerar_peticao_ia(prompt, temperatura=0.7, max_tokens=2000_
