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
import plotly.express as px

# -------------------- Configurações Iniciais --------------------
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configuração da API DeepSeek e do Google Apps Script
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-590cfea82f49426c94ff423d41a91f49")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# Se não houver usuários na sessão, inicia com alguns embutidos
if "USERS" not in st.session_state:
    st.session_state.USERS = {
        "dono": {"username": "dono", "senha": "dono123", "papel": "owner"},
        "gestor1": {"username": "gestor1", "senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A", "area": "Todas"},
        "adv1": {"username": "adv1", "senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Criminal"}
    }

# -------------------- Funções Auxiliares --------------------
def converter_data(data_str):
    """Converte uma string de data no formato ISO para datetime.date."""
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
    """Carrega os dados da planilha do tipo especificado via Google Apps Script."""
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
    """Envia dados (dict) ao Google Apps Script para salvar na planilha."""
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

def carregar_usuarios_da_planilha():
    """
    Carrega os usuários (funcionários) da planilha "Funcionario".
    Retorna um dict indexado por 'usuario'.
    """
    funcionarios = carregar_dados_da_planilha("Funcionario") or []
    users_dict = {}
    if not funcionarios:
        # Se vazio, mantém pelo menos o 'dono'
        users_dict["dono"] = {
            "username": "dono",
            "senha": "dono123",
            "papel": "owner",
            "escritorio": "Global",
            "area": "Todas"
        }
        return users_dict
    for f in funcionarios:
        user_key = f.get("usuario")
        if not user_key:
            continue
        users_dict[user_key] = {
            "username": user_key,
            "senha": f.get("senha", ""),
            "papel": f.get("papel", "assistant"),
            "escritorio": f.get("escritorio", "Global"),
            "area": f.get("area", "Todas")
        }
    return users_dict

def login(usuario, senha):
    """Verifica se (usuario, senha) correspondem a algo em st.session_state.USERS."""
    users = st.session_state.get("USERS", {})
    user = users.get(usuario)
    if user and user["senha"] == senha:
        return user
    return None

def calcular_status_processo(data_prazo, houve_movimentacao, encerrado=False):
    """
    Retorna o status do processo:
      - "⚫ Encerrado" se encerrado=True
      - "🔵 Movimentado" se houve movimentação
      - "🔴 Atrasado" se data_prazo < hoje
      - "🟡 Atenção" se data_prazo - hoje <= 10
      - "🟢 Normal" caso contrário
    """
    if encerrado:
        return "⚫ Encerrado"
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
    """Simulação de consulta de movimentações - busca no site do TJSP (exemplo)."""
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
    """Gera um PDF contendo o 'texto' e salva localmente."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, texto)
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def exportar_docx(texto, nome_arquivo="relatorio"):
    """Gera um DOCX contendo o 'texto' e salva localmente."""
    doc = Document()
    doc.add_paragraph(texto)
    doc.save(f"{nome_arquivo}.docx")
    return f"{nome_arquivo}.docx"

def gerar_relatorio_pdf(dados, nome_arquivo="relatorio"):
    """Gera um relatório PDF a partir de uma lista de dicionários de processos."""
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
        status = calcular_status_processo(
            prazo,
            processo.get("houve_movimentacao", False),
            processo.get("encerrado", False)
        )
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
    """Filtra uma lista de dicionários com base nos valores do dict 'filtros'."""
    def extrair_data(registro):
        data_str = registro.get("data_cadastro") or registro.get("cadastro")
        if data_str:
            try:
                return datetime.date.fromisoformat(data_str[:10])
            except:
                return None
        return None
    
    resultados = []
    for reg in dados:
        incluir = True
        data_reg = extrair_data(reg)
        for campo, valor in filtros.items():
            if not valor:
                continue
            if campo == "data_inicio":
                if data_reg is None or data_reg < valor:
                    incluir = False
                    break
            elif campo == "data_fim":
                if data_reg is None or data_reg > valor:
                    incluir = False
                    break
            else:
                if str(valor).lower() not in str(reg.get(campo, "")).lower():
                    incluir = False
                    break
        if incluir:
            resultados.append(reg)
    return resultados

def atualizar_processo(numero_processo, atualizacoes):
    """Faz a atualização do processo na planilha."""
    atualizacoes["numero"] = numero_processo
    atualizacoes["atualizar"] = True
    return enviar_dados_para_planilha("Processo", atualizacoes)

def excluir_processo(numero_processo):
    """Exclui processo na planilha, definindo 'excluir': True."""
    payload = {"numero": numero_processo, "excluir": True}
    return enviar_dados_para_planilha("Processo", payload)

def get_dataframe_with_cols(data, columns):
    """Garante que o DataFrame contenha determinadas colunas."""
    df = pd.DataFrame(data)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]

##############################
# Interface Principal
##############################
def main():
    st.title("Sistema Jurídico")

    # Atualiza st.session_state.USERS a partir da planilha "Funcionario"
    st.session_state.USERS = carregar_usuarios_da_planilha()

    # Carrega dados das demais abas
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HISTORICO_PETICOES = carregar_dados_da_planilha("Historico_Peticao")
    if not isinstance(HISTORICO_PETICOES, list):
        HISTORICO_PETICOES = []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []

    # ------------------ Sidebar: Login e Logout ------------------ #
    with st.sidebar:
        st.header("🔐 Login")
        usuario_input = st.text_input("Usuário")
        senha_input = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = login(usuario_input, senha_input)
            if user:
                st.session_state.usuario = usuario_input
                st.session_state.papel = user["papel"]
                st.session_state.dados_usuario = user
                st.success("Login realizado com sucesso!")
            else:
                st.error("Credenciais inválidas")

    if "usuario" in st.session_state:
        if st.sidebar.button("Sair"):
            for key in ["usuario", "papel", "dados_usuario"]:
                st.session_state.pop(key, None)
            st.sidebar.success("Você saiu do sistema!")
            st.experimental_rerun()

    # Verifica se o usuário está logado
    if "usuario" in st.session_state:
        papel = st.session_state.papel
        escritorio_usuario = st.session_state.dados_usuario.get("escritorio", "Global")
        area_usuario = st.session_state.dados_usuario.get("area", "Todas")
        st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")

        # Se o usuário for cadastrado com uma única área (ex.: "Criminal"), forçamos esse filtro
        area_fixa = area_usuario if (area_usuario and area_usuario != "Todas") else None

        # Menu Principal
        opcoes = ["Dashboard", "Clientes", "Processos", "Históricos", "Relatórios", "Gerenciar Funcionários"]
        if papel == "owner":
            opcoes.extend(["Gerenciar Escritórios", "Gerenciar Permissões"])
        elif papel == "manager":
            opcoes.extend(["Gerenciar Funcionários"])
        escolha = st.sidebar.selectbox("Menu", opcoes)

        # ------------------ Dashboard ------------------ #
        if escolha == "Dashboard":
            st.subheader("📋 Painel de Controle de Processos")
            with st.expander("🔍 Filtros", expanded=True):
                col1, col2, col3 = st.columns(3)
                if area_fixa:
                    st.info(f"Filtrando pela área: {area_fixa}")
                    filtro_area = area_fixa
                else:
                    filtro_area = st.selectbox("Área", ["Todas"] + list(set(p["area"] for p in PROCESSOS)))
                filtro_status = st.selectbox("Status", ["Todos", "🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado", "⚫ Encerrado"])
                filtro_escritorio = st.selectbox("Escritório", ["Todos"] + list(set(p["escritorio"] for p in PROCESSOS)))
            
            # Aplica filtros
            processos_visiveis = PROCESSOS.copy()
            if area_fixa:
                processos_visiveis = [p for p in processos_visiveis if p.get("area") == area_fixa]
            elif filtro_area != "Todas":
                processos_visiveis = [p for p in processos_visiveis if p.get("area") == filtro_area]
            if filtro_escritorio != "Todos":
                processos_visiveis = [p for p in processos_visiveis if p.get("escritorio") == filtro_escritorio]
            if filtro_status != "Todos":
                if filtro_status == "⚫ Encerrado":
                    processos_visiveis = [p for p in processos_visiveis if p.get("encerrado", False) is True]
                else:
                    processos_visiveis = [
                        p for p in processos_visiveis
                        if calcular_status_processo(
                            converter_data(p.get("prazo")),
                            p.get("houve_movimentacao", False),
                            p.get("encerrado", False)
                        ) == filtro_status
                    ]

            # Visão Geral
            st.subheader("📊 Visão Geral")
            total = len(processos_visiveis)
            atrasados = len([
                p for p in processos_visiveis
                if calcular_status_processo(
                    converter_data(p.get("prazo")),
                    p.get("houve_movimentacao", False),
                    p.get("encerrado", False)
                ) == "🔴 Atrasado"
            ])
            atencao = len([
                p for p in processos_visiveis
                if calcular_status_processo(
                    converter_data(p.get("prazo")),
                    p.get("houve_movimentacao", False),
                    p.get("encerrado", False)
                ) == "🟡 Atenção"
            ])
            movimentados = len([p for p in processos_visiveis if p.get("houve_movimentacao", False)])
            encerrados = len([p for p in processos_visiveis if p.get("encerrado", False) is True])
            
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Total", total)
            col2.metric("Atrasados", atrasados)
            col3.metric("Atenção", atencao)
            col4.metric("Movimentados", movimentados)
            col5.metric("Encerrados", encerrados)

            # Gráfico de Pizza
            if total > 0:
                fig = px.pie(
                    values=[atrasados, atencao, movimentados, encerrados, total - (atrasados + atencao + movimentados + encerrados)],
                    names=["Atrasados", "Atenção", "Movimentados", "Encerrados", "Outros"],
                    title="Distribuição dos Processos",
                    color=["Atrasados", "Atenção", "Movimentados", "Encerrados", "Outros"],
                    color_discrete_map={
                        "Atrasados": "red",
                        "Atenção": "yellow",
                        "Movimentados": "blue",
                        "Encerrados": "black",
                        "Outros": "gray"
                    }
                )
                fig.update_layout(legend_title_text="Status")
                st.plotly_chart(fig)

            st.subheader("📋 Lista de Processos")
            if processos_visiveis:
                df_cols = ["numero", "cliente", "area", "prazo", "responsavel", "link_material"]
                df_proc = get_dataframe_with_cols(processos_visiveis, df_cols)
                df_proc['Status'] = df_proc.apply(lambda row: calcular_status_processo(
                    converter_data(row.get("prazo")),
                    row.get("houve_movimentacao", False),
                    row.get("encerrado", False)
                ), axis=1)
                status_order = {"🔴 Atrasado": 0, "🟡 Atenção": 1, "🟢 Normal": 2, "🔵 Movimentado": 3, "⚫ Encerrado": 4}
                df_proc['Status_Order'] = df_proc['Status'].map(status_order)
                df_proc = df_proc.sort_values('Status_Order').drop('Status_Order', axis=1)
                if "link_material" in df_proc.columns:
                    df_proc["link_material"] = df_proc["link_material"].apply(
                        lambda x: f"[Abrir Material]({x})" if isinstance(x, str) and x.strip() != "" else ""
                    )
                st.dataframe(df_proc)
            else:
                st.info("Nenhum processo encontrado com os filtros aplicados")
            
            st.subheader("✏️ Editar/Excluir Processo")
            num_proc_edit = st.text_input("Digite o número do processo para editar/excluir")
            if num_proc_edit:
                processo_alvo = next((p for p in PROCESSOS if p.get("numero") == num_proc_edit), None)
                if processo_alvo:
                    st.write("Edite os campos abaixo:")
                    novo_cliente = st.text_input("Cliente", processo_alvo.get("cliente", ""))
                    nova_descricao = st.text_area("Descrição", processo_alvo.get("descricao", ""))
                    opcoes_status = ["🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado", "⚫ Encerrado"]
                    try:
                        status_atual = calcular_status_processo(
                            converter_data(processo_alvo.get("prazo")),
                            processo_alvo.get("houve_movimentacao", False),
                            processo_alvo.get("encerrado", False)
                        )
                        indice_inicial = opcoes_status.index(status_atual)
                    except Exception:
                        indice_inicial = 2
                    novo_status = st.selectbox("Status", opcoes_status, index=indice_inicial)
                    novo_link = st.text_input("Link do Material (opcional)", value=processo_alvo.get("link_material", ""))
                    if processo_alvo.get("link_material"):
                        st.markdown(f"[Abrir Material Complementar]({processo_alvo['link_material']})")
                    
                    col_ed, col_exc = st.columns(2)
                    with col_ed:
                        if st.button("Atualizar Processo"):
                            atualizacoes = {
                                "cliente": novo_cliente,
                                "descricao": nova_descricao,
                                "status_manual": novo_status,
                                "link_material": novo_link
                            }
                            if atualizar_processo(num_proc_edit, atualizacoes):
                                st.success("Processo atualizado com sucesso!")
                            else:
                                st.error("Falha ao atualizar processo.")
                    with col_exc:
                        if papel in ["manager", "owner"]:
                            if st.button("Excluir Processo"):
                                if excluir_processo(num_proc_edit):
                                    PROCESSOS = [p for p in PROCESSOS if p.get("numero") != num_proc_edit]
                                    st.success("Processo excluído com sucesso!")
                                else:
                                    st.error("Falha ao excluir processo.")
                else:
                    st.warning("Processo não encontrado.")

        # ------------------ Clientes ------------------ #
        elif escolha == "Clientes":
            st.subheader("👥 Cadastro de Clientes")
            with st.form("form_cliente"):
                nome = st.text_input("Nome Completo*", key="nome_cliente")
                email = st.text_input("E-mail*")
                telefone = st.text_input("Telefone*")
                aniversario = st.date_input("Data de Nascimento")
                endereco = st.text_input("Endereço*", placeholder="Rua, número, bairro, cidade, CEP")
                escritorio = st.selectbox("Escritório", [e["nome"] for e in ESCRITORIOS] + ["Outro"])
                observacoes = st.text_area("Observações")
                if st.form_submit_button("Salvar Cliente"):
                    if not nome or not email or not telefone or not endereco:
                        st.warning("Campos obrigatórios não preenchidos!")
                    else:
                        novo_cliente = {
                            "nome": nome,
                            "email": email,
                            "telefone": telefone,
                            "aniversario": aniversario.strftime("%Y-%m-%d"),
                            "endereco": endereco,
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
                df_cliente = get_dataframe_with_cols(CLIENTES, ["nome", "email", "telefone", "endereco", "cadastro"])
                st.dataframe(df_cliente)
                if st.button("Exportar Relatório em PDF"):
                    texto_relatorio = "\n".join([
                        f'Nome: {c.get("nome", "")} | E-mail: {c.get("email", "")} | Telefone: {c.get("telefone", "")} | Endereço: {c.get("endereco", "")} | Cadastro: {c.get("cadastro", "")}'
                        for c in CLIENTES
                    ])
                    pdf_file = exportar_pdf(texto_relatorio, nome_arquivo="relatorio_clientes")
                    with open(pdf_file, "rb") as f:
                        st.download_button("Baixar PDF", f, file_name=pdf_file)
            else:
                st.info("Nenhum cliente cadastrado.")

        # ------------------ Processos (já implementado) ------------------ #
        elif escolha == "Processos":
            # Mantenha igual
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
                prazo_inicial = st.date_input("Prazo Inicial*", value=datetime.date.today())
                prazo_final = st.date_input("Prazo Final*", value=datetime.date.today() + datetime.timedelta(days=30))
                houve_movimentacao = st.checkbox("Houve movimentação recente?")
                area = st.selectbox("Área Jurídica*", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                if area_usuario and area_usuario != "Todas":
                    st.info(f"Área definida para seu perfil: {area_usuario}")
                    area = area_usuario
                link_material = st.text_input("Link do Material (opcional)")
                encerrado = st.checkbox("Processo Encerrado?")

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
                            "prazo_inicial": prazo_inicial.strftime("%Y-%m-%d"),
                            "prazo": prazo_final.strftime("%Y-%m-%d"),  # Coluna 'prazo' no sheet
                            "houve_movimentacao": houve_movimentacao,
                            "encerrado": encerrado,
                            "escritorio": st.session_state.dados_usuario.get("escritorio", "Global"),
                            "area": area,
                            "responsavel": st.session_state.usuario,
                            "link_material": link_material,
                            "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        if enviar_dados_para_planilha("Processo", novo_processo):
                            PROCESSOS.append(novo_processo)
                            st.success("Processo cadastrado com sucesso!")
            
            st.subheader("Lista de Processos Cadastrados")
            if PROCESSOS:
                df_cols = ["numero", "cliente", "area", "prazo", "responsavel", "link_material"]
                df_proc = get_dataframe_with_cols(PROCESSOS, df_cols)
                df_proc['Status'] = df_proc.apply(lambda row: calcular_status_processo(
                    converter_data(row.get("prazo")),
                    row.get("houve_movimentacao", False),
                    row.get("encerrado", False)
                ), axis=1)
                status_order = {"🔴 Atrasado": 0, "🟡 Atenção": 1, "🟢 Normal": 2, "🔵 Movimentado": 3, "⚫ Encerrado": 4}
                df_proc['Status_Order'] = df_proc['Status'].map(status_order)
                df_proc = df_proc.sort_values('Status_Order').drop('Status_Order', axis=1)
                df_proc["link_material"] = df_proc["link_material"].apply(
                    lambda x: f"[Abrir Material]({x})" if isinstance(x, str) and x.strip() else ""
                )
                st.dataframe(df_proc)
            else:
                st.info("Nenhum processo cadastrado ainda.")

        # ------------------ Históricos (site do TJMG) ------------------ #
        elif escolha == "Históricos":
            st.subheader("📜 Histórico de Processos + Consulta TJMG")
            num_proc = st.text_input("Digite o número do processo para consultar histórico")
            if num_proc:
                historico_filtrado = [h for h in HISTORICO_PETICOES if h.get("numero") == num_proc]
                if historico_filtrado:
                    st.write(f"{len(historico_filtrado)} registro(s) para o processo {num_proc}:")
                    for item in historico_filtrado:
                        with st.expander(f"{item['tipo']} - {item['data']} - {item.get('cliente_associado', '')}"):
                            st.write(f"**Responsável:** {item['responsavel']}")
                            st.write(f"**Escritório:** {item.get('escritorio', '')}")
                            st.text_area("Conteúdo", value=item.get("conteudo", ""), key=item["data"], disabled=True)
                else:
                    st.info("Nenhum histórico encontrado para esse processo.")
            
            st.write("**Consulta TJMG (iframe)**")
            st.components.v1.iframe("https://www.tjmg.jus.br/portal-tjmg/processos/andamento-processual/", height=600)
        
        # ------------------ Relatórios ------------------ #
        elif escolha == "Relatórios":
            st.subheader("📊 Relatórios Personalizados")
            with st.expander("🔍 Filtros Avançados", expanded=True):
                with st.form("form_filtros"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        tipo_relatorio = st.selectbox("Tipo de Relatório*", ["Processos", "Escritórios"])
                        if tipo_relatorio == "Processos":
                            if area_fixa:
                                area_filtro = area_fixa
                                st.info(f"Filtrando pela área: {area_fixa}")
                            else:
                                area_filtro = st.selectbox("Área", ["Todas"] + list(set(p["area"] for p in PROCESSOS)))
                        else:
                            area_filtro = None
                        status_filtro = st.selectbox("Status", ["Todos", "🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado", "⚫ Encerrado"])
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
                                if status_filtro == "⚫ Encerrado":
                                    dados_filtrados = [p for p in dados_filtrados if p.get("encerrado", False)]
                                else:
                                    dados_filtrados = [
                                        p for p in dados_filtrados
                                        if calcular_status_processo(
                                            converter_data(p.get("prazo")),
                                            p.get("houve_movimentacao", False),
                                            p.get("encerrado", False)
                                        ) == status_filtro
                                    ]
                            st.session_state.dados_relatorio = dados_filtrados
                            st.session_state.tipo_relatorio = "Processos"
                        else:
                            dados_filtrados = aplicar_filtros(ESCRITORIOS, filtros)
                            st.session_state.dados_relatorio = dados_filtrados
                            st.session_state.tipo_relatorio = "Escritórios"

            # Exibe e exporta o relatório
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
                            texto = "\n".join([
                                f"{p['numero']} - {p['cliente']}"
                                for p in st.session_state.dados_relatorio
                            ])
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

        # ------------------ Gerenciar Funcionários ------------------ #
        elif escolha == "Gerenciar Funcionários":
            # Mantenha da forma que está no seu script (com exportar txt e pdf)
            st.subheader("👥 Cadastro de Funcionários")
            with st.form("form_funcionario"):
                nome = st.text_input("Nome Completo*")
                email = st.text_input("E-mail*")
                telefone = st.text_input("Telefone*")
                usuario_novo = st.text_input("Usuário*")
                senha_novo = st.text_input("Senha*", type="password")
                escritorio = st.selectbox("Escritório*", [e["nome"] for e in ESCRITORIOS] or ["Global"])
                area_atuacao = st.selectbox("Área de Atuação*", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário", "Todas"])
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
                            "area": area_atuacao,
                            "papel": papel_func,
                            "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "cadastrado_por": st.session_state.usuario
                        }
                        if enviar_dados_para_planilha("Funcionario", novo_funcionario):
                            st.success("Funcionário cadastrado com sucesso!")
                            # Recarrega usuários para mantê-los ativos mesmo após reinício
                            st.session_state.USERS = carregar_usuarios_da_planilha()
            st.subheader("Lista de Funcionários")
            if FUNCIONARIOS:
                if papel == "manager":
                    funcionarios_visiveis = [f for f in FUNCIONARIOS if f.get("escritorio") == escritorio_usuario]
                else:
                    funcionarios_visiveis = FUNCIONARIOS
                if funcionarios_visiveis:
                    df_func = get_dataframe_with_cols(funcionarios_visiveis, ["nome", "email", "telefone", "usuario", "papel", "escritorio", "area"])
                    st.dataframe(df_func)
                    col_export1, col_export2 = st.columns(2)
                    with col_export1:
                        if st.button("Exportar Funcionários (TXT)"):
                            txt = "\n".join([
                                f'{f.get("nome", "")} | {f.get("email", "")} | {f.get("telefone", "")}'
                                for f in funcionarios_visiveis
                            ])
                            st.download_button("Baixar TXT", txt, file_name="funcionarios.txt")
                    with col_export2:
                        if st.button("Exportar Funcionários (PDF)"):
                            texto_pdf = "\n".join([
                                f'{f.get("nome", "")} | {f.get("email", "")} | {f.get("telefone", "")}'
                                for f in funcionarios_visiveis
                            ])
                            pdf_file = exportar_pdf(texto_pdf, nome_arquivo="funcionarios")
                            with open(pdf_file, "rb") as f:
                                st.download_button("Baixar PDF", f, file_name=pdf_file)
                else:
                    st.info("Nenhum funcionário cadastrado para este escritório")
            else:
                st.info("Nenhum funcionário cadastrado ainda")

        # ------------------ Gerenciar Escritórios (Owner) ------------------ #
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
                            if enviar_dados_para_planilha("Escritorio", novo_escritorio):
                                ESCRITORIOS.append(novo_escritorio)
                                st.success("Escritório cadastrado com sucesso!")
            with tab2:
                if ESCRITORIOS:
                    df_esc = get_dataframe_with_cols(ESCRITORIOS, ["nome", "endereco", "telefone", "email", "cnpj"])
                    st.dataframe(df_esc)
                    col_exp1, col_exp2 = st.columns(2)
                    with col_exp1:
                        if st.button("Exportar Escritórios (TXT)"):
                            txt = "\n".join([
                                f'{e.get("nome", "")} | {e.get("endereco", "")} | {e.get("telefone", "")}'
                                for e in ESCRITORIOS
                            ])
                            st.download_button("Baixar TXT", txt, file_name="escritorios.txt")
                    with col_exp2:
                        if st.button("Exportar Escritórios (PDF)"):
                            pdf_file = exportar_pdf("\n".join([
                                f'{e.get("nome", "")} | {e.get("endereco", "")} | {e.get("telefone", "")}'
                                for e in ESCRITORIOS
                            ]), nome_arquivo="escritorios")
                            with open(pdf_file, "rb") as f:
                                st.download_button("Baixar PDF", f, file_name=pdf_file)
                else:
                    st.info("Nenhum escritório cadastrado ainda")
            with tab3:
                st.subheader("Administradores de Escritórios")
                st.info("Aqui podemos cadastrar advogados administradores para cada escritório. (Funcionalidade em desenvolvimento)")

        # ------------------ Gerenciar Permissões (Owner) ------------------ #
        elif escolha == "Gerenciar Permissões" and papel == "owner":
            st.subheader("🔧 Gerenciar Permissões de Funcionários")
            st.info("Configure as áreas de atuação do funcionário, limitando o que ele pode ver.")
            if FUNCIONARIOS:
                df_func = pd.DataFrame(FUNCIONARIOS)
                st.dataframe(df_func)
                funcionario_selecionado = st.selectbox("Funcionário", df_func["nome"].tolist())
                novas_areas = st.multiselect("Áreas Permitidas", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                if st.button("Atualizar Permissões"):
                    atualizado = False
                    for idx, func in enumerate(FUNCIONARIOS):
                        if func.get("nome") == funcionario_selecionado:
                            # Atualiza a "area" dele
                            FUNCIONARIOS[idx]["area"] = ", ".join(novas_areas)
                            atualizado = True
                            # Atualiza no st.session_state.USERS
                            for key, user in st.session_state.USERS.items():
                                # user.get("username") deve ser comparado com "usuario" ou "nome"?
                                # Supondo que "usuario" seja o valor do login, e "nome" seja o "nome" do funcionário
                                # Precisamos achar o user cujo "usuario" eq. func["usuario"]?
                                if user.get("username") == func.get("usuario"):
                                    st.session_state.USERS[key]["area"] = ", ".join(novas_areas)
                    if atualizado:
                        # Envia para planilha
                        # Precisamos atualizar pela "nome" ou "usuario"? Geralmente "usuario" seria a chave
                        # Se a planilha baseia-se em "nome", a chamada seria:
                        # Nome do funcionário => atualiza a col "area"
                        # Mas se a planilha confia em "usuario", então passamos "usuario"?
                        # Seguindo a convenção do script, passamos "nome"
                        if enviar_dados_para_planilha("Funcionario", {
                            "nome": funcionario_selecionado,
                            "area": ", ".join(novas_areas),
                            "atualizar": True
                        }):
                            st.success("Permissões atualizadas com sucesso!")
                        else:
                            st.error("Falha ao atualizar permissões.")
            else:
                st.info("Nenhum funcionário cadastrado.")

    else:
        st.info("Por favor, faça login para acessar o sistema.")

if __name__ == '__main__':
    main()
