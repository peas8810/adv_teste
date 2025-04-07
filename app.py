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

# -------------------- Configurações --------------------
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configuração da API DeepSeek
DEEPSEEK_API_KEY = "sk-4cd98d6c538f42f68bd820a6f3cc44c9"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"

# Dados do sistema
HISTORICO_PETICOES = []
USERS = {
    "dono": {"senha": "dono123", "papel": "owner"},
    "gestor1": {"senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A"},
    "adv1": {"senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Cível"},
}
CLIENTES = []
PROCESSOS = []

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
            
            # Reduz o timeout para 25 segundos com retry automático
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
            if tentativa == tentativas - 1:  # Última tentativa
                raise Exception(f"Erro na requisição: {str(e)}")
            continue
    
    return "❌ Falha ao gerar petição após múltiplas tentativas"

def exportar_pdf(texto, nome_arquivo="documento"):
    """Exporta texto para PDF com formatação melhorada"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Adiciona título
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, nome_arquivo.replace('_', ' ').title(), 0, 1, 'C')
    pdf.ln(10)
    
    # Adiciona conteúdo
    pdf.set_font("Arial", size=12)
    for linha in texto.split("\n"):
        pdf.multi_cell(0, 10, linha)
    
    # Adiciona rodapé
    pdf.set_y(-15)
    pdf.set_font("Arial", 'I', 8)
    pdf.cell(0, 10, f"Gerado em {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 0, 'C')
    
    pdf_path = f"{nome_arquivo}.pdf"
    pdf.output(pdf_path)
    return pdf_path

def exportar_docx(texto, nome_arquivo="documento"):
    """Exporta texto para DOCX com formatação"""
    doc = Document()
    
    # Adiciona título
    doc.add_heading(nome_arquivo.replace('_', ' ').title(), 0)
    
    # Adiciona conteúdo
    for linha in texto.split("\n"):
        doc.add_paragraph(linha)
    
    # Adiciona rodapé
    section = doc.sections[0]
    footer = section.footer
    footer_para = footer.paragraphs[0]
    footer_para.text = f"Gerado em {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}"
    
    docx_path = f"{nome_arquivo}.docx"
    doc.save(docx_path)
    return docx_path

def gerar_relatorio_pdf(dados, titulo="Relatório"):
    """Gera um relatório em PDF formatado"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Cabeçalho
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, titulo, 0, 1, 'C')
    pdf.ln(10)
    
    # Conteúdo
    pdf.set_font("Arial", size=12)
    
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, f"{chave}:", 0, 1)
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, str(valor))
            pdf.ln(5)
    elif isinstance(dados, list):
        for item in dados:
            if isinstance(item, dict):
                for chave, valor in item.items():
                    pdf.set_font("Arial", 'B', 12)
                    pdf.cell(0, 10, f"{chave}:", 0, 1)
                    pdf.set_font("Arial", size=12)
                    pdf.multi_cell(0, 10, str(valor))
                    pdf.ln(5)
            else:
                pdf.multi_cell(0, 10, str(item))
            pdf.ln(5)
    else:
        pdf.multi_cell(0, 10, str(dados))
    
    # Rodapé
    pdf.set_y(-15)
    pdf.set_font("Arial", 'I', 8)
    pdf.cell(0, 10, f"Gerado em {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 0, 'C')
    
    relatorio_path = f"relatorio_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(relatorio_path)
    return relatorio_path

def aplicar_filtros(dados, campos):
    """Aplica filtros aos dados"""
    filtrados = dados
    for campo in campos:
        if campo in dados[0]:
            if "data" in campo.lower():
                col1, col2 = st.columns(2)
                with col1:
                    data_inicio = st.date_input(f"Data inicial de {campo}", value=datetime.date(2000, 1, 1))
                with col2:
                    data_fim = st.date_input(f"Data final de {campo}", value=datetime.date.today())
                filtrados = [d for d in filtrados if campo in d and data_inicio <= datetime.date.fromisoformat(d[campo]) <= data_fim]
            else:
                valor = st.text_input(f"Filtrar por {campo.capitalize()} (deixe em branco para ignorar)")
                if valor:
                    filtrados = [d for d in filtrados if str(d.get(campo, '')).lower() == valor.lower()]
    return filtrados

# -------------------- Interface Principal --------------------
def main():
    st.title("Sistema Jurídico com DeepSeek AI")

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
            opcoes.append("Cadastrar Escritórios")
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
                # Botão para exportar relatório
                if st.button("📊 Exportar Relatório de Processos", key="export_processos"):
                    relatorio_path = gerar_relatorio_pdf(
                        processos_visiveis,
                        "Relatório de Processos"
                    )
                    with open(relatorio_path, "rb") as f:
                        st.download_button(
                            "⬇️ Baixar Relatório PDF",
                            f,
                            file_name=os.path.basename(relatorio_path),
                            mime="application/pdf"
                        )
                
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
                nome = st.text_input("Nome Completo")
                email = st.text_input("E-mail")
                telefone = st.text_input("Telefone")
                aniversario = st.date_input("Data de Nascimento")
                observacoes = st.text_area("Observações")
                
                if st.form_submit_button("Salvar Cliente"):
                    novo_cliente = {
                        "nome": nome,
                        "email": email,
                        "telefone": telefone,
                        "aniversario": aniversario.strftime("%Y-%m-%d"),
                        "observacoes": observacoes,
                        "cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    CLIENTES.append(novo_cliente)
                    st.success("Cliente cadastrado com sucesso!")
            
            # Botão para exportar relatório de clientes
            if CLIENTES:
                if st.button("📊 Exportar Relatório de Clientes", key="export_clientes"):
                    relatorio_path = gerar_relatorio_pdf(
                        CLIENTES,
                        "Relatório de Clientes"
                    )
                    with open(relatorio_path, "rb") as f:
                        st.download_button(
                            "⬇️ Baixar Relatório PDF",
                            f,
                            file_name=os.path.basename(relatorio_path),
                            mime="application/pdf"
                        )

        # Processos
        elif escolha == "Processos":
            st.subheader("📄 Gestão de Processos")
            
            tab1, tab2 = st.tabs(["Cadastrar Processo", "Consultar Andamentos"])
            
            with tab1:
                with st.form("form_processo"):
                    cliente_nome = st.text_input("Cliente")
                    numero_processo = st.text_input("Número do Processo")
                    tipo_contrato = st.selectbox("Tipo de Contrato", ["Fixo", "Por Ato", "Contingência"])
                    descricao = st.text_area("Descrição do Caso")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        valor_total = st.number_input("Valor Total (R$)", min_value=0.0, format="%.2f")
                    with col2:
                        valor_movimentado = st.number_input("Valor Movimentado (R$)", min_value=0.0, format="%.2f")
                    
                    prazo = st.date_input("Prazo Final", value=datetime.date.today() + datetime.timedelta(days=30))
                    houve_movimentacao = st.checkbox("Houve movimentação recente?")
                    area = st.selectbox("Área Jurídica", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                    
                    if st.form_submit_button("Salvar Processo"):
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
                            "responsavel": st.session_state.usuario
                        }
                        PROCESSOS.append(novo_processo)
                        st.success("Processo cadastrado com sucesso!")
            
            with tab2:
                num_consulta = st.text_input("Número do Processo para Consulta")
                if st.button("Consultar Movimentações"):
                    if num_consulta:
                        resultados = consultar_movimentacoes_simples(num_consulta)
                        st.subheader(f"Últimas movimentações do processo {num_consulta}")
                        
                        # Botão para exportar consulta
                        if resultados:
                            relatorio_path = exportar_pdf(
                                "\n".join(resultados),
                                f"consulta_processo_{num_consulta}"
                            )
                            with open(relatorio_path, "rb") as f:
                                st.download_button(
                                    "📄 Exportar Consulta em PDF",
                                    f,
                                    file_name=f"consulta_processo_{num_consulta}.pdf",
                                    mime="application/pdf"
                                )
                        
                        for i, r in enumerate(resultados, 1):
                            st.write(f"{i}. {r}")
                    else:
                        st.warning("Por favor, informe o número do processo")

        # Petições IA
        elif escolha == "Petições IA":
            st.subheader("🤖 Gerador de Petições com DeepSeek AI")
            
            col1, col2 = st.columns([3, 1])
            with col1:
                tipo_peticao = st.selectbox(
                    "Tipo de Documento",
                    ["Petição Inicial", "Contestação", "Recurso", "Memorial", "Outros"],
                    index=0
                )
            with col2:
                formato = st.selectbox("Formato", ["PDF", "DOCX"], index=0)
            
            prompt = st.text_area(
                "Descreva detalhadamente sua necessidade jurídica:",
                placeholder="Ex: 'Preciso de uma petição inicial por danos morais contra uma rede social que permitiu...'",
                height=200
            )
            
            with st.expander("🔧 Configurações Avançadas"):
                col1, col2 = st.columns(2)
                with col1:
                    temperatura = st.slider("Criatividade", 0.1, 1.0, 0.7, 
                                          help="Valores mais altos geram textos mais criativos")
                with col2:
                    max_tokens = st.number_input("Tamanho Máximo", 
                                               min_value=500, 
                                               max_value=4000, 
                                               value=2000,
                                               help="Número máximo de tokens na resposta")
            
            if st.button("🔘 Gerar Petição", use_container_width=True):
                if not prompt.strip():
                    st.warning("Por favor, descreva sua necessidade jurídica")
                else:
                    with st.spinner("Processando sua petição com IA..."):
                        try:
                            # Adiciona contexto jurídico ao prompt
                            prompt_enhanced = f"""
                            Tipo de Documento: {tipo_peticao}
                            Requisitos Jurídicos: {prompt}
                            
                            Por favor, gere um documento jurídico completo com:
                            1. Estrutura formal adequada
                            2. Fundamentação jurídica pertinente
                            3. Linguagem técnica apropriada
                            4. Referências legais quando aplicável
                            """
                            
                            resposta = gerar_peticao_ia(prompt_enhanced, temperatura, max_tokens)
                            
                            if resposta.startswith("❌ Erro"):
                                st.error(resposta)
                            else:
                                # Salva no histórico
                                HISTORICO_PETICOES.append({
                                    "usuario": st.session_state.usuario,
                                    "data": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "tipo": tipo_peticao,
                                    "prompt": prompt,
                                    "resposta": resposta
                                })
                                
                                # Exibe resultado
                                st.subheader("📝 Documento Gerado")
                                st.text_area("", resposta, height=400, key="doc_gerado")
                                
                                # Opções de exportação
                                nome_arquivo = f"peticao_{tipo_peticao.lower().replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d')}"
                                
                                if formato == "PDF":
                                    caminho = exportar_pdf(resposta, nome_arquivo)
                                    with open(caminho, "rb") as f:
                                        st.download_button(
                                            "⬇️ Baixar PDF",
                                            f,
                                            file_name=f"{nome_arquivo}.pdf",
                                            mime="application/pdf"
                                        )
                                else:
                                    caminho = exportar_docx(resposta, nome_arquivo)
                                    with open(caminho, "rb") as f:
                                        st.download_button(
                                            "⬇️ Baixar DOCX",
                                            f,
                                            file_name=f"{nome_arquivo}.docx",
                                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                        )
                                
                                st.success("Documento gerado com sucesso!")
                        
                        except Exception as e:
                            st.error(f"Falha ao gerar petição: {str(e)}")
                            st.info("""
                            Dicas para resolver:
                            1. Verifique sua conexão com a internet
                            2. Tente um prompt mais curto
                            3. Reduza o 'Tamanho máximo' nas configurações
                            4. Tente novamente em alguns minutos
                            """)

        # Histórico
        elif escolha == "Histórico":
            st.subheader("📜 Histórico de Petições")
            
            if not HISTORICO_PETICOES:
                st.info("Nenhuma petição gerada ainda")
            else:
                # Botão para exportar todo o histórico
                if st.button("📊 Exportar Histórico Completo", key="export_historico"):
                    relatorio_path = gerar_relatorio_pdf(
                        HISTORICO_PETICOES,
                        "Histórico Completo de Petições"
                    )
                    with open(relatorio_path, "rb") as f:
                        st.download_button(
                            "⬇️ Baixar Relatório PDF",
                            f,
                            file_name=os.path.basename(relatorio_path),
                            mime="application/pdf"
                        )
                
                for idx, peticao in enumerate(reversed(HISTORICO_PETICOES), 1):
                    with st.expander(f"#{idx} - {peticao['tipo']} ({peticao['data']})"):
                        st.write(f"**Usuário:** {peticao['usuario']}")
                        st.write(f"**Tipo:** {peticao['tipo']}")
                        
                        st.subheader("Prompt Original")
                        st.write(peticao['prompt'])
                        
                        st.subheader("Documento Gerado")
                        st.write(peticao['resposta'])
                        
                        # Opções para cada petição
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"Exportar PDF", key=f"pdf_{idx}"):
                                caminho = exportar_pdf(peticao['resposta'], f"peticao_{idx}")
                                with open(caminho, "rb") as f:
                                    st.download_button(
                                        "Baixar",
                                        f,
                                        file_name=f"peticao_{idx}.pdf",
                                        mime="application/pdf"
                                    )
                        with col2:
                            if st.button(f"Exportar DOCX", key=f"docx_{idx}"):
                                caminho = exportar_docx(peticao['resposta'], f"peticao_{idx}")
                                with open(caminho, "rb") as f:
                                    st.download_button(
                                        "Baixar",
                                        f,
                                        file_name=f"peticao_{idx}.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                    )

        # Relatórios
        elif escolha == "Relatórios":
            st.subheader("📊 Relatórios e Análises")
            
            tipo_relatorio = st.selectbox(
                "Selecione o tipo de relatório",
                ["Processos por Área", "Clientes Ativos", "Petições Geradas", "Financeiro"]
            )
            
            if tipo_relatorio == "Processos por Área":
                areas = {}
                for p in PROCESSOS:
                    if p['area'] in areas:
                        areas[p['area']] += 1
                    else:
                        areas[p['area']] = 1
                
                st.bar_chart(areas)
                
                # Botão para exportar relatório
                if st.button("📄 Exportar Relatório PDF", key="export_processos_area"):
                    relatorio_path = gerar_relatorio_pdf(
                        {"Processos por Área": areas},
                        "Relatório de Processos por Área"
                    )
                    with open(relatorio_path, "rb") as f:
                        st.download_button(
                            "⬇️ Baixar Relatório",
                            f,
                            file_name=os.path.basename(relatorio_path),
                            mime="application/pdf"
                        )
                
            elif tipo_relatorio == "Clientes Ativos":
                st.write("Lista de Clientes:")
                st.dataframe(CLIENTES)
                
                # Botão para exportar relatório
                if st.button("📄 Exportar Relatório PDF", key="export_clientes_ativos"):
                    relatorio_path = gerar_relatorio_pdf(
                        CLIENTES,
                        "Relatório de Clientes Ativos"
                    )
                    with open(relatorio_path, "rb") as f:
                        st.download_button(
                            "⬇️ Baixar Relatório",
                            f,
                            file_name=os.path.basename(relatorio_path),
                            mime="application/pdf"
                        )
                
            elif tipo_relatorio == "Petições Geradas":
                st.write("Estatísticas de Petições:")
                tipos = {}
                for p in HISTORICO_PETICOES:
                    if p['tipo'] in tipos:
                        tipos[p['tipo']] += 1
                    else:
                        tipos[p['tipo']] = 1
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("Total por Tipo:")
                    st.write(tipos)
                with col2:
                    st.write("Últimas 5 Petições:")
                    for p in HISTORICO_PETICOES[-5:]:
                        st.write(f"- {p['tipo']} ({p['data']})")
                
                # Botão para exportar relatório
                if st.button("📄 Exportar Relatório PDF", key="export_peticoes"):
                    relatorio_path = gerar_relatorio_pdf(
                        {
                            "Estatísticas por Tipo": tipos,
                            "Últimas Petições": HISTORICO_PETICOES[-5:]
                        },
                        "Relatório de Petições Geradas"
                    )
                    with open(relatorio_path, "rb") as f:
                        st.download_button(
                            "⬇️ Baixar Relatório",
                            f,
                            file_name=os.path.basename(relatorio_path),
                            mime="application/pdf"
                        )

        # Cadastro de Escritórios (Owner)
        elif escolha == "Cadastrar Escritórios" and papel == "owner":
            st.subheader("🏢 Cadastro de Escritórios")
            
            with st.form("form_escritorio"):
                nome = st.text_input("Nome do Escritório")
                endereco = st.text_input("Endereço")
                telefone = st.text_input("Telefone")
                responsavel = st.text_input("Responsável")
                
                st.markdown("---")
                st.subheader("Criar Usuário Administrador")
                usuario = st.text_input("Usuário")
                senha = st.text_input("Senha", type="password")
                
                if st.form_submit_button("Cadastrar Escritório"):
                    USERS[usuario] = {
                        "senha": senha,
                        "papel": "manager",
                        "escritorio": nome
                    }
                    st.success(f"Escritório {nome} cadastrado com sucesso!")

        # Cadastro de Funcionários (Manager)
        elif escolha == "Cadastrar Funcionários" and papel == "manager":
            st.subheader("👩‍💼 Cadastro de Funcionários")
            
            with st.form("form_funcionario"):
                nome = st.text_input("Nome Completo")
                email = st.text_input("E-mail")
                telefone = st.text_input("Telefone")
                area = st.selectbox("Área de Atuação", ["Cível", "Criminal", "Trabalhista", "Previdenciário"])
                
                st.markdown("---")
                st.subheader("Dados de Acesso")
                usuario = st.text_input("Usuário")
                senha = st.text_input("Senha", type="password")
                
                if st.form_submit_button("Cadastrar Funcionário"):
                    USERS[usuario] = {
                        "senha": senha,
                        "papel": "lawyer",
                        "escritorio": st.session_state.dados_usuario["escritorio"],
                        "area": area,
                        "nome": nome,
                        "email": email,
                        "telefone": telefone
                    }
                    st.success(f"Funcionário {nome} cadastrado com sucesso!")

if __name__ == '__main__':
    main()
