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
import pandas as pd

# -------------------- Configurações Iniciais --------------------
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configuração da API DeepSeek
DEEPSEEK_API_KEY = "sk-4cd98d6c538f42f68bd820a6f3cc44c9"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"

# Configuração do Google Apps Script
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# Dados do sistema
USERS = {
    "dono": {"senha": "dono123", "papel": "owner"},
    "gestor1": {"senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A"},
    "adv1": {"senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Cível"},
}

# -------------------- Funções Auxiliares --------------------
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

# -------------------- Integração com Google Sheets --------------------
def enviar_dados_para_planilha(tipo, dados):
    """
    Envia os dados para o Google Sheets via Google Apps Script.
    Retorna True se a resposta for "OK", caso contrário False.
    """
    try:
        payload = {"tipo": tipo, **dados}
        response = requests.post(
            GAS_WEB_APP_URL,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        return response.text.strip() == "OK"
    except Exception as e:
        st.error(f"❌ Erro ao enviar dados ({tipo}): {e}")
        return False

def carregar_dados_da_planilha(tipo, debug=False):
    """
    Carrega os dados do Google Sheets para o tipo especificado.
    Se debug=True, exibe informações da URL e parte da resposta.
    """
    try:
        response = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo})
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

# -------------------- Funções do Sistema --------------------
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
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    andamentos = soup.find_all("tr", class_="fundocinza1")
    return [a.get_text(strip=True) for a in andamentos[:5]] if andamentos else ["Nenhuma movimentação encontrada"]

def gerar_peticao_ia(prompt, temperatura=0.7, max_tokens=2000, tentativas=3):
    """
    Gera uma petição utilizando a API DeepSeek com tratamento de timeout e tentativas.
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
            with httpx.Client(timeout=30) as client:
                response = client.post(DEEPSEEK_ENDPOINT, headers=headers, json=payload)
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

def exportar_pdf(texto, nome_arquivo="peticao"):
    """
    Exporta o texto informado para um arquivo PDF.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, texto)
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def exportar_docx(texto, nome_arquivo="peticao"):
    """
    Exporta o texto informado para um arquivo DOCX.
    """
    doc = Document()
    doc.add_paragraph(texto)
    doc.save(f"{nome_arquivo}.docx")
    return f"{nome_arquivo}.docx"

def gerar_relatorio_pdf(dados, nome_arquivo="relatorio"):
    """
    Gera um relatório em PDF com uma tabela contendo os dados dos processos.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Título do relatório
    pdf.cell(200, 10, txt="Relatório de Processos", ln=1, align='C')
    pdf.ln(10)
    # Cabeçalho da tabela
    col_widths = [40, 30, 50, 30, 40]
    headers = ["Cliente", "Número", "Área", "Status", "Responsável"]
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 10, txt=header, border=1)
    pdf.ln()
    # Linhas da tabela
    for processo in dados:
        prazo = converter_prazo(processo.get("prazo"))
        status = calcular_status_processo(prazo, processo.get("houve_movimentacao", False))
        cols = [
            processo.get("cliente", ""),
            processo.get("numero", ""),
            processo.get("area", ""),
            status,
            processo.get("responsavel", "")
        ]
        for i, col in enumerate(cols):
            pdf.cell(col_widths[i], 10, txt=str(col), border=1)
        pdf.ln()
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def aplicar_filtros(dados, filtros):
    """
    Aplica os filtros informados aos dados.
    """
    resultados = dados.copy()
    for campo, valor in filtros.items():
        if valor:
            if campo == "data_inicio":
                resultados = [r for r in resultados if datetime.date.fromisoformat(r["data_cadastro"][:10]) >= valor]
            elif campo == "data_fim":
                resultados = [r for r in resultados if datetime.date.fromisoformat(r["data_cadastro"][:10]) <= valor]
            else:
                resultados = [r for r in resultados if str(valor).lower() in str(r.get(campo, "")).lower()]
    return resultados

def verificar_movimentacao_manual(numero_processo):
    """
    Realiza a verificação manual das movimentações do processo especificado.
    """
    with st.spinner(f"Verificando movimentações para o processo {numero_processo}..."):
        time.sleep(2)  # Simula tempo de consulta
        return consultar_movimentacoes_simples(numero_processo)

def obter_processos_por_usuario(papel, escritorio=None, area=None):
    """
    Filtra os processos com base no papel do usuário e, se aplicável, pelo escritório e área.
    """
    processos = carregar_dados_da_planilha("Processo") or []
    if papel == "owner":
        return processos
    elif papel == "manager":
        return [p for p in processos if p.get("escritorio") == escritorio]
    elif papel == "lawyer":
        return [p for p in processos if p.get("escritorio") == escritorio and p.get("area") == area]
    else:
        return []

# -------------------- Interface Principal --------------------
def main():
    st.title("Sistema Jurídico com DeepSeek AI")
    
    # Carregar dados do Google Sheets
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
    
    # Conteúdo principal após login
    if "usuario" in st.session_state:
        papel = st.session_state.papel
        escritorio_usuario = st.session_state.dados_usuario.get("escritorio")
        area_usuario = st.session_state.dados_usuario.get("area")
        st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")
        
        # Menu Principal
        opcoes = ["Dashboard", "Clientes", "Processos", "Petições IA", "Histórico", "Relatórios"]
        if papel == "owner":
            opcoes.extend(["Gerenciar Escritórios", "Gerenciar Funcionários"])
        elif papel == "manager":
            opcoes.extend(["Gerenciar Funcionários"])
        escolha = st.sidebar.selectbox("Menu", opcoes)
        
        # Dashboard
        if escolha == "Dashboard":
            st.subheader("📋 Painel de Controle de Processos")
            with st.expander("🔍 Filtros", expanded=True):
                col1, col2, col3 = st.columns(3)
                with col1:
                    filtro_area = st.selectbox("Área", ["Todas"] + list(set(p["area"] for p in PROCESSOS)))
                with col2:
                    filtro_status = st.selectbox("Status", ["Todos", "🟢 Normal", "🟡 Atenção", "🔴 Atrasado", "🔵 Movimentado"])
                with col3:
                    filtro_escritorio = st.selectbox("Escritório", ["Todos"] + list(set(p["escritorio"] for p in PROCESSOS)))
            
            processos_visiveis = obter_processos_por_usuario(papel, escritorio_usuario, area_usuario)
            if filtro_area != "Todas":
                processos_visiveis = [p for p in processos_visiveis if p.get("area") == filtro_area]
            if filtro_escritorio != "Todos":
                processos_visiveis = [p for p in processos_visiveis if p.get("escritorio") == filtro_escritorio]
            if filtro_status != "Todos":
                processos_visiveis = [
                    p for p in processos_visiveis
                    if calcular_status_processo(converter_prazo(p.get("prazo")), p.get("houve_movimentacao", False)) == filtro_status
                ]
            
            # Métricas Resumidas
            st.subheader("📊 Visão Geral")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Processos", len(processos_visiveis))
            with col2:
                st.metric("Atrasados", len([
                    p for p in processos_visiveis
                    if calcular_status_processo(converter_prazo(p.get("prazo")), p.get("houve_movimentacao", False)) == "🔴 Atrasado"
                ]))
            with col3:
                st.metric("Para Atenção", len([
                    p for p in processos_visiveis
                    if calcular_status_processo(converter_prazo(p.get("prazo")), p.get("houve_movimentacao", False)) == "🟡 Atenção"
                ]))
            with col4:
                st.metric("Movimentados", len([p for p in processos_visiveis if p.get("houve_movimentacao", False)]))
            
            st.subheader("📋 Lista de Processos")
            if processos_visiveis:
                df = pd.DataFrame(processos_visiveis)
                df['Status'] = df.apply(lambda row: calcular_status_processo(
                    converter_prazo(row.get("prazo")), row.get("houve_movimentacao", False)
                ), axis=1)
                status_order = {"🔴 Atrasado": 0, "🟡 Atenção": 1, "🟢 Normal": 2, "🔵 Movimentado": 3}
                df['Status_Order'] = df['Status'].map(status_order)
                df = df.sort_values('Status_Order').drop('Status_Order', axis=1)
                st.dataframe(df[['Status', 'numero', 'cliente', 'area', 'prazo', 'responsavel']])
                
                st.subheader("🔍 Consulta Manual de Processo")
                with st.form("consulta_processo"):
                    num_processo = st.text_input("Número do Processo para Consulta")
                    if st.form_submit_button("Verificar Movimentações"):
                        if num_processo:
                            movimentacoes = verificar_movimentacao_manual(num_processo)
                            st.subheader(f"Movimentações do Processo {num_processo}")
                            for mov in movimentacoes:
                                st.write(f"- {mov}")
                        else:
                            st.warning("Por favor, insira um número de processo")
            else:
                st.info("Nenhum processo encontrado com os filtros aplicados")
        
        # Cadastro de Clientes
        elif escolha == "Clientes":
            st.subheader("👥 Cadastro de Clientes")
            with st.form("form_cliente"):
                nome = st.text_input("Nome Completo*", key="nome_cliente")
                email = st.text_input("E-mail*")
                telefone = st.text_input("Telefone*")
                aniversario = st.date_input("Data de Nascimento")
                escritorio = st.selectbox("Escritório", [e["nome"] for e in ESCRITORIOS] + ["Outro"])
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
                            "responsavel": st.session_state.usuario,
                            "escritorio": escritorio
                        }
                        if enviar_dados_para_planilha("Cliente", novo_cliente):
                            CLIENTES.append(novo_cliente)
                            st.success("Cliente cadastrado com sucesso!")
        
        # Gestão de Processos
        elif escolha == "Processos":
            st.subheader("📄 Gestão de Processos")
            with st.form("form_pro_
