# -------------------- app.py --------------------
# 1. TODAS AS IMPORTAÇÕES PRIMEIRO
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

# 2. IMPORTAÇÃO DO STREAMLIT E CONFIGURAÇÃO DA PÁGINA (DEVE VIR ANTES DE QUALQUER OUTRO COMANDO STREAMLIT)
import streamlit as st
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
import time

# Configuração da API DeepSeek
DEEPSEEK_API_KEY = "sk-4cd98d6c538f42f68bd820a6f3cc44c9"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"

# Configuração do Google Apps Script
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbytp0BA1x2PnjcFhunbgWEoMxZmCobyZHNzq3Mxabr41RScNAH-nYIlBd-OySWv5dcx/exec"

# Dados do sistema
USERS = {
    "dono": {"senha": "dono123", "papel": "owner"},
    "gestor1": {"senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A"},
    "adv1": {"senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Cível"},
}

# -------------------- Funções Auxiliares --------------------
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
            
            with httpx.Client(timeout=30) as client:
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
    """Aplica filtros aos dados"""
    resultados = dados.copy()
    
    for campo, valor in filtros.items():
        if valor and valor not in ["Todas", "Todos"]:
            if campo == "data_inicio":
                resultados = [r for r in resultados if datetime.date.fromisoformat(r.get("data_cadastro", "")[:10]) >= valor]
            elif campo == "data_fim":
                resultados = [r for r in resultados if datetime.date.fromisoformat(r.get("data_cadastro", "")[:10]) <= valor]
            else:
                resultados = [r for r in resultados if str(valor).lower() in str(r.get(campo, "")).lower()]
    
    return resultados

# -------------------- Funções de Páginas --------------------
def mostrar_dashboard():
    """Exibe o dashboard principal"""
    st.subheader("📋 Processos em Andamento")
    
    # Dados simulados para exemplo
    processos_visiveis = [
        {
            "numero": "12345-67.2023.8.26.0100",
            "cliente": "Cliente Exemplo",
            "descricao": "Processo de divórcio consensual",
            "area": "Cível",
            "prazo": (datetime.date.today() + datetime.timedelta(days=15)).isoformat(),
            "valor_total": 5000.00,
            "houve_movimentacao": False,
            "responsavel": "adv1"
        }
    ]
    
    if processos_visiveis:
        for proc in processos_visiveis:
            prazo_default = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
            data_prazo_str = proc.get("prazo", prazo_default)
            data_prazo = datetime.date.fromisoformat(data_prazo_str)
            movimentacao = proc.get("houve_movimentacao", False)
            status = calcular_status_processo(data_prazo, movimentacao)
            
            with st.expander(f"{status} Processo: {proc['numero']}"):
                st.write(f"**Cliente:** {proc.get('cliente', '')}")
                st.write(f"**Descrição:** {proc.get('descricao', '')}")
                st.write(f"**Área:** {proc.get('area', '')}")
                st.write(f"**Prazo:** {data_prazo.strftime('%d/%m/%Y')}")
                st.write(f"**Valor:** R$ {proc.get('valor_total', 0):,.2f}")
    else:
        st.info("Nenhum processo cadastrado.")

def cadastrar_clientes():
    """Página de cadastro de clientes"""
    st.subheader("👥 Cadastro de Clientes")
    
    with st.form("form_cliente", clear_on_submit=True):
        nome = st.text_input("Nome Completo*", key="nome_cliente")
        email = st.text_input("E-mail*")
        telefone = st.text_input("Telefone*")
        aniversario = st.date_input("Data de Nascimento")
        escritorio = st.selectbox("Escritório", ["Escritorio A", "Escritorio B", "Outro"])
        observacoes = st.text_area("Observações")
        
        submitted = st.form_submit_button("Salvar Cliente")
        
        if submitted:
            if not nome or not email or not telefone:
                st.warning("Campos obrigatórios (*) não preenchidos!")
            else:
                st.success(f"Cliente {nome} cadastrado com sucesso!")

def cadastrar_processos():
    """Página de cadastro de processos"""
    st.subheader("📄 Gestão de Processos")
    
    with st.form("form_processo", clear_on_submit=True):
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
        
        submitted = st.form_submit_button("Salvar Processo")
        
        if submitted:
            if not cliente_nome or not numero_processo or not descricao:
                st.warning("Campos obrigatórios (*) não preenchidos!")
            else:
                st.success(f"Processo {numero_processo} cadastrado com sucesso!")

def gerar_peticoes_ia():
    """Página de geração de petições com IA"""
    st.subheader("🤖 Gerador de Petições com IA")
    
    # Dados simulados para exemplo
    clientes = ["Cliente A", "Cliente B", "Cliente C"]
    
    with st.form("form_peticao"):
        tipo_peticao = st.selectbox("Tipo de Petição*", [
            "Inicial Cível",
            "Resposta",
            "Recurso",
            "Memorial",
            "Contestação"
        ])
        
        cliente_associado = st.selectbox("Cliente Associado", clientes + ["Nenhum"])
        contexto = st.text_area("Descreva o caso*", 
                              help="Forneça detalhes sobre o caso, partes envolvidas, documentos relevantes etc.")
        
        col1, col2 = st.columns(2)
        with col1:
            estilo = st.selectbox("Estilo de Redação*", ["Objetivo", "Persuasivo", "Técnico", "Detalhado"])
        with col2:
            parametros = st.slider("Nível de Detalhe", 0.1, 1.0, 0.7)
        
        submitted = st.form_submit_button("Gerar Petição")
    
    if submitted:
        if not contexto or not tipo_peticao:
            st.warning("Campos obrigatórios (*) não preenchidos!")
        else:
            try:
                with st.spinner("Gerando petição com IA (pode levar alguns minutos)..."):
                    # Simulação de resposta da IA
                    resposta_simulada = f"""
                    EXMO. SR. DR. JUIZ DE DIREITO DA __ VARA CÍVEL DA COMARCA DE __

                    {st.session_state.usuario}, advogado(a), inscrito(a) na OAB/__ sob o n.º __, no exercício de seu munus, vem respeitosamente perante V. Exa. propor a presente AÇÃO DE {tipo_peticao.upper()}, em face de {cliente_associado if cliente_associado != "Nenhum" else "CLIENTE NÃO IDENTIFICADO"}, pelos fatos e fundamentos a seguir expostos:

                    1. DOS FATOS
                    {contexto[:200]}...

                    2. DO DIREITO
                    A matéria em questão encontra amparo nos arts. __ do Código Civil...

                    3. DO PEDIDO
                    Diante do exposto, requer a V. Exa. seja deferido o pedido para...

                    Nestes termos,
                    Pede deferimento.
                    """
                    
                    st.session_state.ultima_peticao = resposta_simulada
                    st.success("Petição gerada com sucesso!")
                
                st.text_area("Petição Gerada", value=resposta_simulada, height=400, key="peticao_gerada")
                
                # Botões de exportação
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Exportar para PDF"):
                        pdf_file = exportar_pdf(resposta_simulada)
                        with open(pdf_file, "rb") as f:
                            st.download_button(
                                "Baixar PDF",
                                f,
                                file_name=f"peticao_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
                            )
                with col2:
                    if st.button("Exportar para DOCX"):
                        docx_file = exportar_docx(resposta_simulada)
                        with open(docx_file, "rb") as f:
                            st.download_button(
                                "Baixar DOCX",
                                f,
                                file_name=f"peticao_{datetime.datetime.now().strftime('%Y%m%d')}.docx"
                            )
            
            except Exception as e:
                st.error(f"Erro ao gerar petição: {str(e)}")

def historico_peticoes():
    """Página de histórico de petições"""
    st.subheader("📜 Histórico de Petições")
    
    # Dados simulados para exemplo
    historico = [
        {
            "tipo": "Inicial Cível",
            "data": "2023-10-15 14:30:00",
            "responsavel": "adv1",
            "conteudo": "Petição de divórcio consensual...",
            "cliente_associado": "Cliente A"
        }
    ]
    
    if historico:
        for item in reversed(historico):
            with st.expander(f"{item['tipo']} - {item['data']} - {item.get('cliente_associado', '')}"):
                st.write(f"**Responsável:** {item['responsavel']}")
                st.text_area("Conteúdo", value=item['conteudo'], key=item['data'], disabled=True)
    else:
        st.info("Nenhuma petição gerada ainda")

def gerar_relatorios():
    """Página de geração de relatórios"""
    st.subheader("📊 Relatórios")
    
    # Dados simulados para exemplo
    processos = [
        {
            "cliente": "Cliente A",
            "numero": "12345-67.2023.8.26.0100",
            "area": "Cível",
            "prazo": (datetime.date.today() + datetime.timedelta(days=5)).isoformat(),
            "houve_movimentacao": False,
            "responsavel": "adv1",
            "data_cadastro": "2023-10-01 09:15:00"
        }
    ]
    
    with st.form("form_filtros"):
        st.write("Filtrar por:")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            area_filtro = st.selectbox("Área", ["Todas"] + list(set(p.get("area", "") for p in processos)))
            status_filtro = st.selectbox("Status", ["Todos", "🟢", "🟡", "🔴", "🔵"])
        
        with col2:
            escritorio_filtro = st.selectbox("Escritório", ["Todos"] + list(set(p.get("escritorio", "") for p in processos)))
            responsavel_filtro = st.selectbox("Responsável", ["Todos"] + list(set(p.get("responsavel", "") for p in processos)))
        
        with col3:
            data_inicio = st.date_input("Data Início")
            data_fim = st.date_input("Data Fim")
        
        submitted = st.form_submit_button("Aplicar Filtros")
    
    if submitted:
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
        
        processos_filtrados = aplicar_filtros(processos, filtros)
        
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
                st.download_button("Baixar Relatório", f, file_name=arquivo)
        
        st.dataframe(st.session_state.processos_filtrados)
    else:
        st.info("Nenhum processo encontrado com os filtros aplicados")

def cadastrar_escritorios():
    """Página de cadastro de escritórios"""
    st.subheader("🏢 Cadastrar Escritório")
    
    with st.form("form_escritorio", clear_on_submit=True):
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
        
        submitted = st.form_submit_button("Salvar Escritório")
        
        if submitted:
            campos_obrigatorios = [
                nome, endereco, telefone, email, cnpj,
                responsavel_tecnico, telefone_tecnico, email_tecnico
            ]
            
            if not all(campos_obrigatorios):
                st.warning("Todos os campos obrigatórios (*) devem ser preenchidos!")
            else:
                st.success(f"Escritório {nome} cadastrado com sucesso!")

def gerenciar_escritorios():
    """Página de gerenciamento de escritórios"""
    st.subheader("🏢 Gerenciar Escritórios")
    
    # Dados simulados para exemplo
    escritorios = [
        {
            "nome": "Escritorio A",
            "endereco": "Rua Exemplo, 123",
            "telefone": "(11) 9999-9999",
            "email": "contato@escritorioa.com",
            "cnpj": "12.345.678/0001-90"
        }
    ]
    
    tab1, tab2 = st.tabs(["Cadastrar Escritório", "Lista de Escritórios"])
    
    with tab1:
        cadastrar_escritorios()
    
    with tab2:
        if escritorios:
            st.dataframe(escritorios)
        else:
            st.info("Nenhum escritório cadastrado ainda")

def cadastrar_funcionarios():
    """Página de cadastro de funcionários"""
    st.subheader("👥 Cadastrar Funcionário")
    
    with st.form("form_funcionario", clear_on_submit=True):
        nome = st.text_input("Nome Completo*")
        email = st.text_input("E-mail*")
        telefone = st.text_input("Telefone*")
        papel = st.selectbox("Cargo*", ["Advogado", "Estagiário", "Secretário"])
        area_atuacao = st.selectbox("Área de Atuação", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
        escritorio = st.selectbox("Escritório*", ["Escritorio A", "Escritorio B"])
        
        submitted = st.form_submit_button("Salvar Funcionário")
        
        if submitted:
            if not nome or not email or not telefone or not papel or not escritorio:
                st.warning("Todos os campos obrigatórios (*) devem ser preenchidos!")
            else:
                st.success(f"Funcionário {nome} cadastrado com sucesso!")

# -------------------- APP principal --------------------
def main():
    st.set_page_config(page_title="Sistema Jurídico", layout="wide")
    st.title("Sistema Jurídico com IA e Prazos Inteligentes")

    with st.sidebar:
        st.header("Login")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = login(usuario, senha)
            if user:
                st.session_state.usuario = usuario
                st.session_state.papel = user["papel"]
                st.session_state.dados_usuario = user
            else:
                st.error("Usuário ou senha incorretos")

    if "usuario" in st.session_state:
        papel = st.session_state.papel
        st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")

        # UI baseada na hierarquia
        opcoes = ["Dashboard", "Clientes", "Processos", "Petições IA", "Histórico", "Relatórios"]
        if papel == "owner":
            opcoes.extend(["Cadastrar Escritórios", "Gerenciar Escritórios"])
        elif papel == "manager":
            opcoes.append("Cadastrar Funcionários")

        escolha = st.sidebar.selectbox("Menu", opcoes)

        # Dashboard
        if escolha == "Dashboard":
            mostrar_dashboard()

        elif escolha == "Clientes":
            cadastrar_clientes()

        elif escolha == "Processos":
            cadastrar_processos()

        elif escolha == "Petições IA":
            gerar_peticoes_ia()

        elif escolha == "Histórico":
            historico_peticoes()

        elif escolha == "Relatórios":
            gerar_relatorios()

        elif escolha == "Cadastrar Escritórios":
            cadastrar_escritorios()

        elif escolha == "Gerenciar Escritórios":
            gerenciar_escritorios()

        elif escolha == "Cadastrar Funcionários":
            cadastrar_funcionarios()

if __name__ == '__main__':
    main()
