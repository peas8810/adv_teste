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

# Configuração da API DeepSeek e do Google Apps Script
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-590cfea82f49426c94ff423d41a91f49")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# Dados do sistema (usuários) – cada usuário possui "username" e "senha"
if "USERS" not in st.session_state:
    st.session_state.USERS = {
        "dono": {"username": "dono", "senha": "dono123", "papel": "owner", "area": "Todas"},
        "gestor1": {"username": "gestor1", "senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A", "area": "Todas"},
        "adv1": {"username": "adv1", "senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Criminal"}
    }

# -------------------- Funções Auxiliares --------------------
def converter_data(data_str):
    if not data_str:
        return datetime.date.today()
    try:
        data_str = data_str.replace("Z", "")
        if "T" in data_str:
            return datetime.datetime.fromisoformat(data_str).date()
        return datetime.date.fromisoformat(data_str)
    except Exception:
        return datetime.date.today()

@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados_da_planilha(tipo, debug=False):
    try:
        response = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo}, timeout=10)
        response.raise_for_status()
        if debug:
            st.text(f"URL chamada: {response.url}")
            st.text(f"Resposta bruta: {response.text[:500]}")
        return response.json()
    except Exception as e:
        st.error(f"Erro ao carregar dados ({tipo}): {e}")
        return []

def enviar_dados_para_planilha(tipo, dados):
    try:
        payload = {"tipo": tipo, **dados}
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            response = client.post(GAS_WEB_APP_URL, json=payload)
        if response.text.strip() == "OK":
            return True
        else:
            st.error(f"Erro no envio: {response.text}")
            return False
    except Exception as e:
        st.error(f"Erro ao enviar dados ({tipo}): {e}")
        return False

def login(usuario, senha):
    users = st.session_state.get("USERS", {})
    for user in users.values():
        if user.get("username") == usuario and user.get("senha") == senha:
            return user
    return None

def calcular_status_processo(data_prazo, houve_movimentacao):
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
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={numero_processo}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        andamentos = soup.find_all("tr", class_="fundocinza1")
        if andamentos:
            return [a.get_text(strip=True) for a in andamentos[:5]]
        else:
            return ["Nenhuma movimentação encontrada"]
    except:
        return ["Erro ao consultar movimentações"]

def exportar_pdf(texto, nome_arquivo="relatorio"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, texto)
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def exportar_docx(texto, nome_arquivo="relatorio"):
    doc = Document()
    doc.add_paragraph(texto)
    doc.save(f"{nome_arquivo}.docx")
    return f"{nome_arquivo}.docx"

def gerar_relatorio_pdf(dados, nome_arquivo="relatorio"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Relatório de Processos", ln=1, align='C')
    pdf.ln(10)
    col_widths = [40, 30, 50, 30, 40]
    headers = ["Cliente", "Número", "Área", "Status", "Responsável"]
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 10, txt=header, border=1)
    pdf.ln()
    for processo in dados:
        prazo = converter_data(processo.get("prazo"))
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
    def extrair_data(r):
        data_str = r.get("data_cadastro") or r.get("cadastro")
        if data_str:
            try:
                return datetime.date.fromisoformat(data_str[:10])
            except:
                return None
        return None
    resultados = []
    for r in dados:
        incluir = True
        data_r = extrair_data(r)
        for campo, valor in filtros.items():
            if not valor:
                continue
            if campo == "data_inicio":
                if data_r is None or data_r < valor:
                    incluir = False
                    break
            elif campo == "data_fim":
                if data_r is None or data_r > valor:
                    incluir = False
                    break
            else:
                if str(valor).lower() not in str(r.get(campo, "")).lower():
                    incluir = False
                    break
        if incluir:
            resultados.append(r)
    return resultados

def atualizar_processo(numero_processo, atualizacoes):
    atualizacoes["numero"] = numero_processo
    atualizacoes["atualizar"] = True
    return enviar_dados_para_planilha("Processo", atualizacoes)

def excluir_processo(numero_processo):
    payload = {"numero": numero_processo, "excluir": True}
    return enviar_dados_para_planilha("Processo", payload)

# -------------------- Interface Principal --------------------
def main():
    st.title("Sistema Jurídico")
    
    # Inicializa usuários persistidos na sessão, se ainda não houver
    if "USERS" not in st.session_state:
        st.session_state.USERS = USERS

    # Carregamento dos dados
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HISTORICO_PETICOES = carregar_dados_da_planilha("Historico_Peticao")
    if not isinstance(HISTORICO_PETICOES, list):
        HISTORICO_PETICOES = []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario")
    if not isinstance(FUNCIONARIOS, list):
        FUNCIONARIOS = []
    
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
    
    # Botão de Logout
    if "usuario" in st.session_state:
        if st.sidebar.button("Sair"):
            for key in ["usuario", "papel", "dados_usuario"]:
                st.session_state.pop(key, None)
            st.sidebar.success("Você saiu do sistema!")
            st.experimental_rerun()
    
    if "usuario" in st.session_state:
        papel = st.session_state.papel
        escritorio_usuario = st.session_state.dados_usuario.get("escritorio")
        area_usuario = st.session_state.dados_usuario.get("area")
        st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")
        
        # Menu Principal
        opcoes = ["Dashboard", "Clientes", "Processos", "Históricos", "Relatórios", "Gerenciar Funcionários"]
        if papel == "owner":
            opcoes.extend(["Gerenciar Escritórios", "Gerenciar Permissões"])
        elif papel == "manager":
            opcoes.extend(["Gerenciar Funcionários"])
        escolha = st.sidebar.selectbox("Menu", opcoes)
        
        # ----------------- Aba Dashboard: Visualiza, Filtra, Edição e Exclusão de Processos -----------------
        if escolha == "Dashboard":
            st.subheader("📋 Painel de Controle de Processos")
            with st.expander("🔍 Filtros", expanded=True):
                col1, col2, col3 = st.columns(3)
                with col1:
                    # Se o usuário tiver uma área específica, só será exibida essa opção
                    if area_usuario and area_usuario != "Todas":
                        filtro_area = st.selectbox("Área", [area_usuario])
                    else:
                        filtro_area = st.selectbox("Área", ["Todas"] + list(set(p["area"] for p in PROCESSOS)))
                with col2:
                    filtro_status = st.selectbox("Status", ["Todos", "🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado"])
                with col3:
                    filtro_escritorio = st.selectbox("Escritório", ["Todos"] + list(set(p["escritorio"] for p in PROCESSOS)))
            processos_visiveis = PROCESSOS.copy()
            # Filtra com base na área do usuário, se aplicável
            if area_usuario and area_usuario != "Todas":
                processos_visiveis = [p for p in processos_visiveis if p.get("area") == area_usuario]
            if filtro_area != "Todas":
                processos_visiveis = [p for p in processos_visiveis if p.get("area") == filtro_area]
            if filtro_escritorio != "Todos":
                processos_visiveis = [p for p in processos_visiveis if p.get("escritorio") == filtro_escritorio]
            if filtro_status != "Todos":
                processos_visiveis = [p for p in processos_visiveis 
                                       if calcular_status_processo(converter_data(p.get("prazo")),
                                                                   p.get("houve_movimentacao", False)) == filtro_status]
            st.subheader("📊 Visão Geral")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Processos", len(processos_visiveis))
            with col2:
                st.metric("Atrasados", len([p for p in processos_visiveis 
                                            if calcular_status_processo(converter_data(p.get("prazo")),
                                                                        p.get("houve_movimentacao", False)) == "🔴 Atrasado"]))
            with col3:
                st.metric("Para Atenção", len([p for p in processos_visiveis 
                                               if calcular_status_processo(converter_data(p.get("prazo")),
                                                                           p.get("houve_movimentacao", False)) == "🟡 Atenção"]))
            with col4:
                st.metric("Movimentados", len([p for p in processos_visiveis if p.get("houve_movimentacao", False)]))
            st.subheader("📋 Lista de Processos")
            if processos_visiveis:
                df = pd.DataFrame(processos_visiveis)
                df['Status'] = df.apply(lambda row: calcular_status_processo(
                                            converter_data(row.get("prazo")),
                                            row.get("houve_movimentacao", False)), axis=1)
                status_order = {"🔴 Atrasado": 0, "🟡 Atenção": 1, "🟢 Normal": 2, "🔵 Movimentado": 3}
                df['Status_Order'] = df['Status'].map(status_order)
                df = df.sort_values('Status_Order').drop('Status_Order', axis=1)
                st.dataframe(df[['numero', 'cliente', 'area', 'prazo', 'responsavel', 'Status']])
            else:
                st.info("Nenhum processo encontrado com os filtros aplicados")
            
            st.subheader("✏️ Editar/Excluir Processo")
            num_proc_editar = st.text_input("Digite o número do processo para editar/excluir")
            if num_proc_editar:
                proc = next((p for p in PROCESSOS if p.get("numero") == num_proc_editar), None)
                if proc:
                    st.write("Edite os campos abaixo:")
                    novo_cliente = st.text_input("Cliente", proc.get("cliente", ""))
                    nova_descricao = st.text_area("Descrição", proc.get("descricao", ""))
                    opcoes_status = ["🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado"]
                    try:
                        status_atual = calcular_status_processo(converter_data(proc.get("prazo")),
                                                                proc.get("houve_movimentacao", False))
                        indice_inicial = opcoes_status.index(status_atual)
                    except Exception:
                        indice_inicial = 2
                    novo_status = st.selectbox("Status", opcoes_status, index=indice_inicial)
                    # Novo campo: link do material complementar
                    novo_link = st.text_input("Link do Material Complementar (opcional)", value=proc.get("link_material", ""))
                    if proc.get("link_material"):
                        st.markdown(f"[Baixar Material Complementar]({proc.get('link_material')})")
                    col_edit, col
