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

# Estrutura das planilhas no Google Sheets
SHEETS_CONFIG = {
    "Clientes": {
        "columns": ["nome", "email", "telefone", "aniversario", "observacoes", "cadastro", "responsavel", "escritorio"]
    },
    "Processos": {
        "columns": ["cliente", "numero", "tipo", "descricao", "valor_total", "valor_movimentado", 
                   "prazo", "houve_movimentacao", "escritorio", "area", "responsavel", "data_cadastro"]
    },
    "Escritorios": {
        "columns": ["nome", "endereco", "telefone", "email", "cnpj", "data_cadastro", "responsavel",
                   "responsavel_tecnico", "telefone_tecnico", "email_tecnico", "area_atuacao"]
    },
    "Historico_Peticoes": {
        "columns": ["tipo", "data", "responsavel", "conteudo", "escritorio", "cliente_associado"]
    }
}

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
                worksheet.append_row(SHEETS_CONFIG[sheet_name]["columns"])
            
            if isinstance(dados, dict):
                # Converte o dicionário para lista na ordem das colunas
                row_data = [dados.get(col, "") for col in SHEETS_CONFIG[sheet_name]["columns"]]
                worksheet.append_row(row_data)
            elif isinstance(dados, list):
                # Para listas de dicionários
                rows_data = [[item.get(col, "") for col in SHEETS_CONFIG[sheet_name]["columns"]] for item in dados]
                worksheet.append_rows(rows_data)
            
            st.success(f"Dados salvos com sucesso na aba {sheet_name}!")
    except Exception as e:
        st.error(f"Erro ao salvar dados: {e}")

def carregar_dados(sheet_name):
    """Carrega dados de uma aba específica"""
    try:
        spreadsheet = conectar_google_sheets()
        if spreadsheet:
            worksheet = spreadsheet.worksheet(sheet_name)
            records = worksheet.get_all_records()
            return records
    except Exception as e:
        st.warning(f"Nenhum dado encontrado na aba {sheet_name} ou erro ao carregar: {e}")
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
                "content": "Você é um assistente jurídico especializado em direito brasileiro. Responda com linguagem técnica formal, cite artigos de lei e jurisprudência relevante quando aplicável. Estruture a petição com: 1. Preâmbulo 2. Fatos 3. Fundamentação Jurídica 4. Pedido."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": temperatura,
        "max_tokens": max_tokens,
        "stream": False
    }
    
    for tentativa in range(tentativas):
        try:
            start_time = time.time()
            
            with httpx.Client(timeout=30.0) as client:
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
            wait_time = (tentativa + 1) * 5  # Backoff exponencial
            st.warning(f"Tentativa {tentativa + 1} falhou (timeout). Aguardando {wait_time}s...")
            time.sleep(wait_time)
            continue
                
        except httpx.HTTPStatusError as e:
            error_msg = f"Erro HTTP {e.response.status_code}"
            if e.response.status_code == 402:
                error_msg += " - Saldo insuficiente na API"
            raise Exception(f"{error_msg}: {e.response.text}")
            
        except Exception as e:
            if tentativa == tentativas - 1:
                raise Exception(f"Erro na requisição: {str(e)}")
            time.sleep(3)
            continue
    
    return "❌ Falha ao gerar petição após múltiplas tentativas"

def exportar_pdf(texto, nome_arquivo="peticao"):
    """Exporta texto para PDF"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, texto)
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def exportar_docx(texto, nome_arquivo="peticao"):
    """Exporta texto para DOCX"""
    doc = Document()
    doc.add_paragraph(texto)
    doc.save(f"{nome_arquivo}.docx")
    return f"{nome_arquivo}.docx"

def gerar_relatorio_pdf(dados, nome_arquivo="relatorio"):
    """Gera relatório em PDF com tabela de dados"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Título
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
        prazo = datetime.date.fromisoformat(processo.get("prazo", datetime.date.today().isoformat()))
        status = calcular_status_processo(prazo, processo.get("houve_movimentacao", False))
        
        cols = [
            processo["cliente"],
            processo["numero"],
            processo["area"],
            status,
            processo["responsavel"]
        ]
        
        for i, col in enumerate(cols):
            pdf.cell(col_widths[i], 10, txt=str(col), border=1)
        pdf.ln()
    
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def aplicar_filtros(dados, filtros):
    """Aplica filtros aos dados"""
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

# -------------------- Interface Principal --------------------
def main():
    st.title("Sistema Jurídico com DeepSeek AI")

    # Carrega dados do Google Sheets
    CLIENTES = carregar_dados("Clientes") or []
    PROCESSOS = carregar_dados("Processos") or []
    ESCRITORIOS = carregar_dados("Escritorios") or []
    HISTORICO_PETICOES = carregar_dados("Historico_Peticoes") or []

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
                escritorio = st.selectbox("Escritório*", [e["nome"] for e in ESCRITORIOS] + ["Outro"])
                observacoes = st.text_area("Observações")
                
                if st.form_submit_button("Salvar Cliente"):
                    if not nome or not email or not telefone or not escritorio:
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
                        campos_obrigatorios = [
                            nome, endereco, telefone, email, cnpj,
                            responsavel_tecnico, telefone_tecnico, email_tecnico
                        ]
                        
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
                            ESCRITORIOS.append(novo_escritorio)
                            salvar_dados("Escritorios", novo_escritorio)
                            st.success("Escritório cadastrado com sucesso!")
            
            with tab2:
                if ESCRITORIOS:
                    st.dataframe(ESCRITORIOS)
                else:
                    st.info("Nenhum escritório cadastrado ainda")

        # Petições IA
        elif escolha == "Petições IA":
            st.subheader("🤖 Gerador de Petições com IA")
            
            with st.form("form_peticao"):
                tipo_peticao = st.selectbox("Tipo de Petição*", [
                    "Inicial Cível",
                    "Resposta",
                    "Recurso",
                    "Memorial",
                    "Contestação",
                    "Ação Declaratória",
                    "Ação de Execução",
                    "Ação Possessória"
                ])
                
                cliente_associado = st.selectbox("Cliente Associado", [c["nome"] for c in CLIENTES] + ["Nenhum"])
                contexto = st.text_area("Descreva o caso*", 
                                      help="Forneça detalhes sobre o caso, partes envolvidas, documentos relevantes, artigos de lei aplicáveis etc.")
                
                col1, col2 = st.columns(2)
                with col1:
                    estilo = st.selectbox("Estilo de Redação*", ["Objetivo", "Persuasivo", "Técnico", "Detalhado"])
                with col2:
                    parametros = st.slider("Nível de Detalhe", 0.1, 1.0, 0.7)
                
                if st.form_submit_button("Gerar Petição"):
                    if not contexto or not tipo_peticao:
                        st.warning("Campos obrigatórios (*) não preenchidos!")
                    else:
                        prompt = f"""
                        Gere uma petição jurídica do tipo {tipo_peticao} com os seguintes detalhes:

                        **Contexto do Caso:**
                        {contexto}

                        **Requisitos:**
                        - Estilo: {estilo}
                        - Linguagem jurídica formal brasileira
                        - Estruturada com: 1. Preâmbulo 2. Fatos 3. Fundamentação Jurídica 4. Pedido
                        - Cite artigos de lei e jurisprudência quando aplicável
                        - Inclua fecho padrão (Nestes termos, pede deferimento)
                        - Limite de {int(2000*parametros)} tokens
                        """
                        
                        try:
                            with st.spinner("Gerando petição com IA (pode levar alguns minutos)..."):
                                resposta = gerar_peticao_ia(prompt, temperatura=parametros)
                                st.session_state.ultima_peticao = resposta
                                st.session_state.prompt_usado = prompt
                                
                                # Salva no histórico
                                nova_peticao = {
                                    "tipo": tipo_peticao,
                                    "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "responsavel": st.session_state.usuario,
                                    "conteudo": resposta[:1000] + "..." if len(resposta) > 1000 else resposta,
                                    "escritorio": st.session_state.dados_usuario.get("escritorio", "Global"),
                                    "cliente_associado": cliente_associado if cliente_associado != "Nenhum" else ""
                                }
                                HISTORICO_PETICOES.append(nova_peticao)
                                salvar_dados("Historico_Peticoes", nova_peticao)
                            
                            st.success("Petição gerada com sucesso!")
                            st.text_area("Petição Gerada", value=resposta, height=400)
                            
                            # Opções de exportação
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("Exportar para PDF"):
                                    arquivo = exportar_pdf(resposta)
                                    with open(arquivo, "rb") as f:
                                        st.download_button("Baixar PDF", f, file_name=f"peticao_{datetime.datetime.now().strftime('%Y%m%d')}.pdf")
                            with col2:
                                if st.button("Exportar para DOCX"):
                                    arquivo = exportar_docx(resposta)
                                    with open(arquivo, "rb") as f:
                                        st.download_button("Baixar DOCX", f, file_name=f"peticao_{datetime.datetime.now().strftime('%Y%m%d')}.docx")
                            
                        except Exception as e:
                            st.error(f"Erro ao gerar petição: {str(e)}")

        # Histórico
        elif escolha == "Histórico":
            st.subheader("📜 Histórico de Petições")
            
            if HISTORICO_PETICOES:
                for item in reversed(HISTORICO_PETICOES):
                    with st.expander(f"{item['tipo']} - {item['data']} - {item['cliente_associado'] or 'Sem cliente associado'}"):
                        st.write(f"**Responsável:** {item['responsavel']}")
                        st.write(f"**Escritório:** {item['escritorio']}")
                        st.text_area("Conteúdo", value=item['conteudo'], key=item['data'], disabled=True, height=200)
            else:
                st.info("Nenhuma petição gerada ainda")

        # Relatórios
        elif escolha == "Relatórios":
            st.subheader("📊 Relatórios")
            
            with st.form("form_filtros"):
                st.write("Filtrar por:")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    area_filtro = st.selectbox("Área", ["Todas"] + list(set(p["area"] for p in PROCESSOS)))
                    status_filtro = st.selectbox("Status", ["Todos", "🟢", "🟡", "🔴", "🔵"])
                
                with col2:
                    escritorio_filtro = st.selectbox("Escritório", ["Todos"] + list(set(p["escritorio"] for p in PROCESSOS)))
                    responsavel_filtro = st.selectbox("Responsável", ["Todos"] + list(set(p["responsavel"] for p in PROCESSOS)))
                
                with col3:
                    data_inicio = st.date_input("Data Início")
                    data_fim = st.date_input("Data Fim")
                
                if st.form_submit_button("Aplicar Filtros"):
                    filtros = {}
                    if area_filtro != "Todas":
                        filtros["area"] = area_filtro
                    if escritorio_filtro != "Todos":
                        filtros["escritorio"] = escritorio_filtro
                    if responsavel_filtro != "Todos":
                        filtros["responsavel"] = responsavel_filtro
                    if data_inicio:
                        filtros["data_inicio"] = data_inicio
                    if data_fim:
                        filtros["data_fim"] = data_fim
                    
                    processos_filtrados = aplicar_filtros(PROCESSOS, filtros)
                    
                    # Filtro adicional por status
                    if status_filtro != "Todos":
                        processos_filtrados = [
                            p for p in processos_filtrados 
                            if calcular_status_processo(
                                datetime.date.fromisoformat(p.get("prazo", datetime.date.today().isoformat())),
                                p.get("houve_movimentacao", False)
                            ) == status_filtro
                        ]
                    
                    st.session_state.processos_filtrados = processos_filtrados
            
            if "processos_filtrados" in st.session_state and st.session_state.processos_filtrados:
                st.write(f"Processos encontrados: {len(st.session_state.processos_filtrados)}")
                
                if st.button("Gerar Relatório PDF"):
                    arquivo = gerar_relatorio_pdf(st.session_state.processos_filtrados)
                    with open(arquivo, "rb") as f:
                        st.download_button("Baixar Relatório", f, file_name=f"relatorio_{datetime.datetime.now().strftime('%Y%m%d')}.pdf")
                
                st.dataframe(st.session_state.processos_filtrados)
            else:
                st.info("Nenhum processo encontrado com os filtros aplicados")

if __name__ == '__main__':
    main()
