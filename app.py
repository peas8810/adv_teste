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
import tempfile

# Imports para integração com Google Drive
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# -------------------- Configurações Iniciais --------------------
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configuração da API DeepSeek e do Google Apps Script
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-590cfea82f49426c94ff423d41a91f49")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# Dados do sistema (usuários) – cada usuário possui "username" e "senha"
USERS = {
    "dono": {"username": "dono", "senha": "dono123", "papel": "owner"},
    "gestor1": {"username": "gestor1", "senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A", "area": "Todas"},
    "adv1": {"username": "adv1", "senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Cível"},
}

# -------------------- Funções de Integração com Google Drive --------------------
def get_drive_service():
    """
    Cria e retorna um objeto de serviço da API Google Drive.
    Usa OAuth2 para obtenção de credenciais e passa a chave API (developerKey) para o serviço.
    As credenciais são armazenadas em 'token.json'. Em ambientes sem navegador, 
    utiliza run_local_server(open_browser=False) para que a URL de autorização seja exibida sem abrir o navegador.
    """
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    client_config = {
        "installed": {
            "client_id": "911153011494-sof7lv46kqrt0av3dmob23otqdvsjjji.apps.googleusercontent.com",
            "client_secret": "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",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }
    creds = None
    token_path = "token.json"
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(requests.Request())
            except Exception as e:
                st.error(f"Erro ao atualizar credenciais: {e}")
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
            with open(token_path, "w") as token:
                token.write(creds.to_json())
    # Adiciona a chave API (developerKey) ao criar o serviço
    service = build('drive', 'v3', credentials=creds, developerKey="AIzaSyDMOOy0wHxO-Es9aQ2WHrZTedinKeEOaXo")
    return service

def upload_to_drive(file, nome_arquivo):
    """
    Faz upload do arquivo para uma pasta específica no Google Drive.
    A pasta destino é definida pelo folder_id (extraído da URL do Drive).
    Retorna o ID do arquivo enviado.
    """
    try:
        service = get_drive_service()
        temp_path = os.path.join(tempfile.gettempdir(), nome_arquivo)
        with open(temp_path, "wb") as f:
            f.write(file.getbuffer())
        folder_id = "1NZDsgzvP-st_g9etp6hyGorqgyCDOrCK"
        file_metadata = {"name": nome_arquivo, "parents": [folder_id]}
        media = MediaFileUpload(temp_path, resumable=True)
        uploaded = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        return uploaded.get("id")
    except Exception as e:
        st.error(f"Erro ao fazer upload para o Drive: {e}")
        return ""

# -------------------- Outras Funções Auxiliares --------------------
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
    for user in USERS.values():
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
    
    # Opção de Sair do Sistema
    if "usuario" in st.session_state:
        if st.sidebar.button("Sair"):
            for key in ["usuario", "papel", "dados_usuario"]:
                if key in st.session_state:
                    del st.session_state[key]
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
                    filtro_area = st.selectbox("Área", ["Todas"] + list(set(p["area"] for p in PROCESSOS)))
                with col2:
                    filtro_status = st.selectbox("Status", ["Todos", "🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado"])
                with col3:
                    filtro_escritorio = st.selectbox("Escritório", ["Todos"] + list(set(p["escritorio"] for p in PROCESSOS)))
            processos_visiveis = PROCESSOS.copy()
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
                        status_atual = calcular_status_processo(converter_data(proc.get("prazo")), proc.get("houve_movimentacao", False))
                        indice_inicial = opcoes_status.index(status_atual)
                    except Exception:
                        indice_inicial = 2
                    novo_status = st.selectbox("Status", opcoes_status, index=indice_inicial)
                    novo_anexo = st.file_uploader("Novo Anexo (opcional)", type=["pdf", "docx", "jpg", "png"])
                    # Se houver anexo já cadastrado, exibe link para download
                    if proc.get("anexo"):
                        download_url = f"https://drive.google.com/uc?export=download&id={proc.get('anexo')}"
                        st.markdown(f"[Baixar Anexo Atual]({download_url})")
                    col_edit, col_excluir = st.columns(2)
                    with col_edit:
                        if st.button("Atualizar Processo"):
                            atualizacoes = {
                                "cliente": novo_cliente,
                                "descricao": nova_descricao,
                                "status_manual": novo_status
                            }
                            if novo_anexo is not None:
                                anexo_nome = upload_to_drive(novo_anexo, f"anexo_{num_proc_editar}_{novo_anexo.name}")
                                atualizacoes["anexo"] = anexo_nome
                            if atualizar_processo(num_proc_editar, atualizacoes):
                                st.success("Processo atualizado com sucesso!")
                            else:
                                st.error("Falha ao atualizar processo.")
                    with col_excluir:
                        if papel in ["manager", "owner"]:
                            if st.button("Excluir Processo"):
                                if excluir_processo(num_proc_editar):
                                    PROCESSOS = [p for p in PROCESSOS if p.get("numero") != num_proc_editar]
                                    st.success("Processo excluído com sucesso!")
                                else:
                                    st.error("Falha ao excluir processo.")
                else:
                    st.warning("Processo não encontrado.")
        
        # ----------------- Aba Processos: Cadastro de Novo Processo -----------------
        elif escolha == "Processos":
            st.subheader("📄 Cadastro de Processos")
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
                arquivo_proc = st.file_uploader("Anexar Documento (será enviado para o Drive)", type=["pdf", "docx", "jpg", "png"])
                if st.form_submit_button("Salvar Processo"):
                    if not cliente_nome or not numero_processo or not descricao:
                        st.warning("Campos obrigatórios (*) não preenchidos!")
                    else:
                        if arquivo_proc is not None:
                            anexo_path = upload_to_drive(arquivo_proc, f"anexo_{numero_processo}_{arquivo_proc.name}")
                        else:
                            anexo_path = ""
                        novo_processo = {
                            "cliente": cliente_nome,
                            "numero": numero_processo,
                            "contrato": tipo_contrato,
                            "descricao": descricao,
                            "valor_total": valor_total,
                            "valor_movimentado": valor_movimentado,
                            "prazo": prazo.strftime("%Y-%m-%d"),
                            "houve_movimentacao": houve_movimentacao,
                            "escritorio": st.session_state.dados_usuario.get("escritorio", "Global"),
                            "area": area,
                            "responsavel": st.session_state.usuario,
                            "anexo": anexo_path,
                            "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        if enviar_dados_para_planilha("Processo", novo_processo):
                            PROCESSOS.append(novo_processo)
                            st.success("Processo cadastrado com sucesso!")
            st.subheader("Lista de Processos Cadastrados")
            if PROCESSOS:
                st.dataframe(pd.DataFrame(PROCESSOS))
            else:
                st.info("Nenhum processo cadastrado ainda.")
        
        # ----------------- Aba Clientes: Cadastro e Relatório -----------------
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
                        st.warning("Campos obrigatórios não preenchidos!")
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
            st.subheader("Lista de Clientes e Relatório")
            if CLIENTES:
                st.dataframe(pd.DataFrame(CLIENTES))
                if st.button("Exportar Relatório em PDF"):
                    texto_relatorio = "\n".join([
                        f'Nome: {c.get("nome", "")} | E-mail: {c.get("email", "")} | Telefone: {c.get("telefone", "")} | Cadastro: {c.get("cadastro", "")}'
                        for c in CLIENTES
                    ])
                    pdf_file = exportar_pdf(texto_relatorio, nome_arquivo="relatorio_clientes")
                    with open(pdf_file, "rb") as f:
                        st.download_button("Baixar PDF", f, file_name=pdf_file)
            else:
                st.info("Nenhum cliente cadastrado.")
        
        # ----------------- Aba Históricos: Pesquisa de Histórico de Processos -----------------
        elif escolha == "Históricos":
            st.subheader("📜 Histórico de Movimentação de Processos")
            num_proc = st.text_input("Digite o número do processo para pesquisar o histórico")
            if num_proc:
                historico = [h for h in HISTORICO_PETICOES if h.get("numero") == num_proc]
                if historico:
                    st.write(f"{len(historico)} registro(s) encontrado(s) para o processo {num_proc}:")
                    for item in historico:
                        with st.expander(f"{item['tipo']} - {item['data']} - {item.get('cliente_associado', '')}"):
                            st.write(f"**Responsável:** {item['responsavel']}")
                            st.write(f"**Escritório:** {item.get('escritorio', '')}")
                            st.text_area("Conteúdo", value=item.get("conteudo", ""), key=item["data"], disabled=True)
                else:
                    st.info("Nenhum histórico encontrado para este processo.")
        
        # ----------------- Aba Relatórios: Processos e Escritórios -----------------
        elif escolha == "Relatórios":
            st.subheader("📊 Relatórios Personalizados")
            with st.expander("🔍 Filtros Avançados", expanded=True):
                with st.form("form_filtros"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        tipo_relatorio = st.selectbox("Tipo de Relatório*", ["Processos", "Escritórios"])
                        if tipo_relatorio == "Processos":
                            area_filtro = st.selectbox("Área", ["Todas"] + list(set(p["area"] for p in PROCESSOS)))
                        else:
                            area_filtro = None
                        status_filtro = st.selectbox("Status", ["Todos", "🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado"])
                    with col2:
                        escritorio_filtro = st.selectbox("Escritório", ["Todos"] + list(set(p["escritorio"] for p in PROCESSOS)))
                        responsavel_filtro = st.selectbox("Responsável", ["Todos"] + list(set(p["responsavel"] for p in PROCESSOS)))
                    with col3:
                        data_inicio = st.date_input("Data Início")
                        data_fim = st.date_input("Data Fim")
                        formato_exportacao = st.selectbox("Formato de Exportação", ["PDF", "DOCX", "CSV"])
                    if st.form_submit_button("Aplicar Filtros"):
                        filtros = {}
                        if area_filtro and area_filtro != "Todas":
                            filtros["area"] = area_filtro
                        if escritorio_filtro != "Todos":
                            filtros["escritorio"] = escritorio_filtro
                        if responsavel_filtro != "Todos":
                            filtros["responsavel"] = responsavel_filtro
                        if data_inicio:
                            filtros["data_inicio"] = data_inicio
                        if data_fim:
                            filtros["data_fim"] = data_fim
                        
                        if tipo_relatorio == "Processos":
                            dados_filtrados = aplicar_filtros(PROCESSOS, filtros)
                            if status_filtro != "Todos":
                                dados_filtrados = [
                                    p for p in dados_filtrados
                                    if calcular_status_processo(converter_data(p.get("prazo")), p.get("houve_movimentacao", False)) == status_filtro
                                ]
                            st.session_state.dados_relatorio = dados_filtrados
                            st.session_state.tipo_relatorio = "Processos"
                        else:
                            dados_filtrados = aplicar_filtros(ESCRITORIOS, filtros)
                            st.session_state.dados_relatorio = dados_filtrados
                            st.session_state.tipo_relatorio = "Escritórios"
            if "dados_relatorio" in st.session_state and st.session_state.dados_relatorio:
                st.write(f"{st.session_state.tipo_relatorio} encontrados: {len(st.session_state.dados_relatorio)}")
                if st.button(f"Exportar Relatório ({formato_exportacao})"):
                    if formato_exportacao == "PDF":
                        if st.session_state.tipo_relatorio == "Processos":
                            arquivo = gerar_relatorio_pdf(st.session_state.dados_relatorio)
                        else:
                            arquivo = exportar_pdf(str(st.session_state.dados_relatorio))
                        with open(arquivo, "rb") as f:
                            st.download_button("Baixar PDF", f, file_name=arquivo)
                    elif formato_exportacao == "DOCX":
                        if st.session_state.tipo_relatorio == "Processos":
                            texto = "\n".join([f"{p['numero']} - {p['cliente']}" for p in st.session_state.dados_relatorio])
                        else:
                            texto = str(st.session_state.dados_relatorio)
                        arquivo = exportar_docx(texto)
                        with open(arquivo, "rb") as f:
                            st.download_button("Baixar DOCX", f, file_name=arquivo)
                    elif formato_exportacao == "CSV":
                        df_export = pd.DataFrame(st.session_state.dados_relatorio)
                        csv_bytes = df_export.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "Baixar CSV",
                            data=csv_bytes,
                            file_name=f"relatorio_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
                        st.dataframe(st.session_state.dados_relatorio)
                    else:
                        st.info("Nenhum dado encontrado com os filtros aplicados")
        
        # ----------------- Aba Gerenciar Funcionários: Cadastro, Listagem e Exclusão -----------------
        elif escolha == "Gerenciar Funcionários":
            st.subheader("👥 Cadastro de Funcionários")
            with st.form("form_funcionario"):
                nome = st.text_input("Nome Completo*")
                email = st.text_input("E-mail*")
                telefone = st.text_input("Telefone*")
                usuario_novo = st.text_input("Usuário*")
                senha_novo = st.text_input("Senha*", type="password")
                escritorio = st.selectbox("Escritório*", [e["nome"] for e in ESCRITORIOS])
                area_atuacao = st.selectbox("Área de Atuação*", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                papel_func = st.selectbox("Papel no Sistema*", ["manager", "lawyer", "assistant"])
                if st.form_submit_button("Cadastrar Funcionário"):
                    if not nome or not email or not telefone or not usuario_novo or not senha_novo:
                        st.warning("Campos obrigatórios não preenchidos!")
                    else:
                        novo_funcionario = {
                            "nome": nome,
                            "email": email,
                            "telefone": telefone,
                            "usuario": usuario_novo,
                            "senha": senha_novo,
                            "escritorio": escritorio,
                            "area_atuacao": area_atuacao,
                            "papel": papel_func,
                            "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "cadastrado_por": st.session_state.usuario
                        }
                        if enviar_dados_para_planilha("Funcionario", novo_funcionario):
                            FUNCIONARIOS.append(novo_funcionario)
                            USERS[usuario_novo] = {
                                "username": usuario_novo,
                                "senha": senha_novo,
                                "papel": papel_func,
                                "escritorio": escritorio,
                                "area": area_atuacao
                            }
                            st.success("Funcionário cadastrado com sucesso!")
            st.subheader("Lista de Funcionários")
            if FUNCIONARIOS:
                if papel == "manager":
                    funcionarios_visiveis = [f for f in FUNCIONARIOS if f.get("escritorio") == escritorio_usuario]
                else:
                    funcionarios_visiveis = FUNCIONARIOS
                if funcionarios_visiveis:
                    st.dataframe(pd.DataFrame(funcionarios_visiveis))
                    if papel == "manager":
                        func_excluir = st.selectbox("Selecione o Funcionário para exclusão", pd.DataFrame(funcionarios_visiveis)["nome"].tolist())
                        if st.button("Excluir Funcionário"):
                            FUNCIONARIOS = [f for f in FUNCIONARIOS if f.get("nome") != func_excluir]
                            USERS.pop(func_excluir, None)
                            if enviar_dados_para_planilha("Funcionario", {"nome": func_excluir, "excluir": True}):
                                st.success("Funcionário excluído com sucesso!")
                            else:
                                st.error("Falha ao excluir funcionário.")
                else:
                    st.info("Nenhum funcionário cadastrado para este escritório")
            else:
                st.info("Nenhum funcionário cadastrado ainda")
        
        # ----------------- Aba Gerenciar Escritórios (Owner) -----------------
        elif escolha == "Gerenciar Escritórios" and papel == "owner":
            st.subheader("🏢 Gerenciamento de Escritórios")
            tab1, tab2, tab3 = st.tabs(["Cadastrar Escritório", "Lista de Escritórios", "Administradores"])
            with tab1:
                with st.form("form_escritorio"):
                    st.subheader("Dados Cadastrais")
                    nome = st.text_input("Nome do Escritório*")
                    endereco = st.text_input("Endereço Completo*")
                    telefone = st.text_input("Telefone*")
                    email = st.text_input("E-mail*")
                    cnpj = st.text_input("CNPJ*")
                    st.subheader("Responsável Técnico")
                    responsavel_tecnico = st.text_input("Nome do Responsável Técnico*")
                    telefone_tecnico = st.text_input("Telefone do Responsável*")
                    email_tecnico = st.text_input("E-mail do Responsável*")
                    area_atuacao = st.multiselect("Áreas de Atuação", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                    if st.form_submit_button("Salvar Escritório"):
                        campos_obrigatorios = [nome, endereco, telefone, email, cnpj, responsavel_tecnico, telefone_tecnico, email_tecnico]
                        if not all(campos_obrigatorios):
                            st.warning("Todos os campos obrigatórios (*) devem ser preenchidos!")
                        else:
                            novo_escritorio = {
                                "nome": nome,
                                "endereco": endereco,
                                "telefone": telefone,
                                "email": email,
                                "cnpj": cnpj,
                                "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "responsavel": st.session_state.usuario,
                                "responsavel_tecnico": responsavel_tecnico,
                                "telefone_tecnico": telefone_tecnico,
                                "email_tecnico": email_tecnico,
                                "area_atuacao": ", ".join(area_atuacao)
                            }
                            if enviar_dados_para_planilha("Escritorio", novo_escritorio):
                                ESCRITORIOS.append(novo_escritorio)
                                st.success("Escritório cadastrado com sucesso!")
            with tab2:
                if ESCRITORIOS:
                    st.dataframe(pd.DataFrame(ESCRITORIOS))
                else:
                    st.info("Nenhum escritório cadastrado ainda")
            with tab3:
                st.subheader("Administradores de Escritórios")
                st.info("Funcionalidade em desenvolvimento - Aqui será possível cadastrar administradores para cada escritório")
        
        # ----------------- Aba Gerenciar Permissões (Owner) -----------------
        elif escolha == "Gerenciar Permissões" and papel == "owner":
            st.subheader("🔧 Gerenciar Permissões de Funcionários")
            st.info("Altere as áreas/permissões dos funcionários:")
            if FUNCIONARIOS:
                df_func = pd.DataFrame(FUNCIONARIOS)
                st.dataframe(df_func)
                funcionario_selecionado = st.selectbox("Funcionário", df_func["nome"].tolist())
                novas_areas = st.multiselect("Áreas Permitidas", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                if st.button("Atualizar Permissões"):
                    atualizado = False
                    for idx, func in enumerate(FUNCIONARIOS):
                        if func.get("nome") == funcionario_selecionado:
                            FUNCIONARIOS[idx]["area_atuacao"] = ", ".join(novas_areas)
                            atualizado = True
                            for key, user in USERS.items():
                                if user.get("username") == funcionario_selecionado:
                                    USERS[key]["area"] = ", ".join(novas_areas)
                    if atualizado:
                        if enviar_dados_para_planilha("Funcionario", {"nome": funcionario_selecionado, "area_atuacao": ", ".join(novas_areas), "atualizar": True}):
                            st.success("Permissões atualizadas com sucesso!")
                        else:
                            st.error("Falha ao atualizar permissões.")
            else:
                st.info("Nenhum funcionário cadastrado.")
        
        # A aba "Petições IA" foi removida conforme solicitado.
        
if __name__ == '__main__':
    main()
