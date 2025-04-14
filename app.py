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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-590cfea82f49426c94ff423d41a91f49")
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
    Converte uma string de data no formato ISO para um objeto date.
    Se o valor for nulo ou estiver em formato inválido, retorna a data de hoje.
    """
    if not prazo_str:
        return datetime.date.today()
    try:
        # Remover o "Z" final, se existir
        prazo_str = prazo_str.replace("Z", "")
        # Se contém "T", então é uma data e hora; vamos converter e pegar apenas a data
        if "T" in prazo_str:
            dt = datetime.datetime.fromisoformat(prazo_str)
            return dt.date()
        else:
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
        with httpx.Client(timeout=10, follow_redirects=True) as client:
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

def gerar_peticao_ia(prompt, temperatura=0.7, max_tokens=2000, tentativas=3):
    """
    Gera uma petição utilizando a API DeepSeek com tratamento de timeout e tentativas.
    """
    # Configuração da chave de API e do endpoint conforme a documentação DeepSeek.
    DEEPSEEK_API_KEY = "sk-51096de13c2c4da6b81bb6574f515982"
    DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
    
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
        "max_tokens": max_tokens,
        "stream": False  # Não utiliza streaming, conforme documentação.
    }
    
    for tentativa in range(tentativas):
        try:
            start_time = time.time()
            with httpx.Client(timeout=60) as client:
                response = client.post(DEEPSEEK_ENDPOINT, headers=headers, json=payload)
            tempo_resposta = time.time() - start_time
            st.sidebar.metric("Tempo de resposta API", f"{tempo_resposta:.2f}s")
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
    
   # Carregar dados do Google Sheets com cache para melhorar performance
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
                            "contrato": tipo_contrato,
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
                        if enviar_dados_para_planilha("Processo", novo_processo):
                            PROCESSOS.append(novo_processo)
                            st.success("Processo cadastrado com sucesso!")
        
        # Gerenciamento de Escritórios (Owner)
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
                    st.dataframe(ESCRITORIOS)
                else:
                    st.info("Nenhum escritório cadastrado ainda")
            with tab3:
                st.subheader("Administradores de Escritórios")
                st.info("Funcionalidade em desenvolvimento - Aqui será possível cadastrar administradores para cada escritório")
        
        # Gerenciamento de Funcionários (Owner e Manager)
        elif escolha == "Gerenciar Funcionários" and papel in ["owner", "manager"]:
            st.subheader("👥 Cadastro de Funcionários")
            with st.form("form_funcionario"):
                nome = st.text_input("Nome Completo*")
                email = st.text_input("E-mail*")
                telefone = st.text_input("Telefone*")
                escritorio = st.selectbox("Escritório*", [e["nome"] for e in ESCRITORIOS])
                area_atuacao = st.selectbox("Área de Atuação*", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                papel_func = st.selectbox("Papel no Sistema*", ["manager", "lawyer", "assistant"])
                if st.form_submit_button("Cadastrar Funcionário"):
                    if not nome or not email or not telefone:
                        st.warning("Campos obrigatórios (*) não preenchidos!")
                    else:
                        novo_funcionario = {
                            "nome": nome,
                            "email": email,
                            "telefone": telefone,
                            "escritorio": escritorio,
                            "area_atuacao": area_atuacao,
                            "papel": papel_func,
                            "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "cadastrado_por": st.session_state.usuario
                        }
                        if enviar_dados_para_planilha("Funcionario", novo_funcionario):
                            FUNCIONARIOS.append(novo_funcionario)
                            st.success("Funcionário cadastrado com sucesso!")
            st.subheader("Lista de Funcionários")
            if FUNCIONARIOS:
                if papel == "manager":
                    funcionarios_visiveis = [f for f in FUNCIONARIOS if f.get("escritorio") == escritorio_usuario]
                else:
                    funcionarios_visiveis = FUNCIONARIOS
                if funcionarios_visiveis:
                    st.dataframe(funcionarios_visiveis)
                else:
                    st.info("Nenhum funcionário cadastrado para este escritório")
            else:
                st.info("Nenhum funcionário cadastrado ainda")
        
        # Gerador de Petições com IA
        elif escolha == "Petições IA":
            st.subheader("🤖 Gerador de Petições com IA")
            with st.form("form_peticao"):
                tipo_peticao = st.selectbox("Tipo de Petição*", [
                    "Inicial Cível",
                    "Resposta",
                    "Recurso",
                    "Memorial",
                    "Contestação"
                ])
                cliente_associado = st.selectbox("Cliente Associado", [c["nome"] for c in CLIENTES] + ["Nenhum"])
                contexto = st.text_area("Descreva o caso*", help="Forneça detalhes sobre o caso, partes envolvidas, documentos relevantes etc.")
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
                    - Limite de {int(2000 * parametros)} tokens
                    """
                    try:
                        with st.spinner("Gerando petição com IA (pode levar alguns minutos)..."):
                            resposta = gerar_peticao_ia(prompt, temperatura=parametros)
                            st.session_state.ultima_peticao = resposta
                            st.session_state.prompt_usado = prompt
                            nova_peticao = {
                                "tipo": tipo_peticao,
                                "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "responsavel": st.session_state.usuario,
                                "conteudo": resposta[:1000] + "..." if len(resposta) > 1000 else resposta,
                                "escritorio": st.session_state.dados_usuario.get("escritorio", "Global"),
                                "cliente_associado": cliente_associado if cliente_associado != "Nenhum" else ""
                            }
                            if enviar_dados_para_planilha("Historico_Peticao", nova_peticao):
                                HISTORICO_PETICOES.append(nova_peticao)
                                st.success("Petição gerada e salva com sucesso!")
                        st.text_area("Petição Gerada", value=resposta, height=400, key="peticao_gerada")
                    except Exception as e:
                        st.error(f"Erro ao gerar petição: {str(e)}")
            if 'ultima_peticao' in st.session_state:
                col1, col2 = st.columns(2)
                with col1:
                    pdf_file = exportar_pdf(st.session_state.ultima_peticao)
                    with open(pdf_file, "rb") as f:
                        st.download_button("Exportar para PDF", f, file_name=f"peticao_{datetime.datetime.now().strftime('%Y%m%d')}.pdf", key="download_pdf")
                with col2:
                    docx_file = exportar_docx(st.session_state.ultima_peticao)
                    with open(docx_file, "rb") as f:
                        st.download_button("Exportar para DOCX", f, file_name=f"peticao_{datetime.datetime.now().strftime('%Y%m%d')}.docx", key="download_docx")
        
        # Histórico de Petições
        elif escolha == "Histórico":
            st.subheader("📜 Histórico de Petições")
            if HISTORICO_PETICOES:
                for item in reversed(HISTORICO_PETICOES):
                    with st.expander(f"{item['tipo']} - {item['data']} - {item.get('cliente_associado', '')}"):
                        st.write(f"**Responsável:** {item['responsavel']}")
                        st.write(f"**Escritório:** {item.get('escritorio', '')}")
                        st.text_area("Conteúdo", value=item['conteudo'], key=item['data'], disabled=True)
            else:
                st.info("Nenhuma petição gerada ainda")
        
        # Relatórios Personalizados
        elif escolha == "Relatórios":
            st.subheader("📊 Relatórios Personalizados")
            with st.expander("🔍 Filtros Avançados", expanded=True):
                with st.form("form_filtros"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        tipo_relatorio = st.selectbox("Tipo de Relatório*", ["Processos", "Clientes", "Escritórios"])
                        area_filtro = st.selectbox("Área", ["Todas"] + list(set(p["area"] for p in PROCESSOS)))
                        status_filtro = st.selectbox("Status", ["Todos", "🟢 Normal", "🟡 Atenção", "🔴 Atrasado", "🔵 Movimentado"])
                    with col2:
                        escritorio_filtro = st.selectbox("Escritório", ["Todos"] + list(set(p["escritorio"] for p in PROCESSOS)))
                        responsavel_filtro = st.selectbox("Responsável", ["Todos"] + list(set(p["responsavel"] for p in PROCESSOS)))
                    with col3:
                        data_inicio = st.date_input("Data Início")
                        data_fim = st.date_input("Data Fim")
                        formato_exportacao = st.selectbox("Formato de Exportação", ["PDF", "DOCX", "CSV"])
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
                        if tipo_relatorio == "Processos":
                            dados_filtrados = aplicar_filtros(PROCESSOS, filtros)
                            if status_filtro != "Todos":
                                dados_filtrados = [
                                    p for p in dados_filtrados
                                    if calcular_status_processo(converter_prazo(p.get("prazo")), p.get("houve_movimentacao", False)) == status_filtro
                                ]
                            st.session_state.dados_relatorio = dados_filtrados
                            st.session_state.tipo_relatorio = "Processos"
                        elif tipo_relatorio == "Clientes":
                            dados_filtrados = aplicar_filtros(CLIENTES, filtros)
                            st.session_state.dados_relatorio = dados_filtrados
                            st.session_state.tipo_relatorio = "Clientes"
                        elif tipo_relatorio == "Escritórios":
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

if __name__ == '__main__':
    main()
