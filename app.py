import streamlit as st
import datetime
import time
import httpx
import requests
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from fpdf import FPDF
from docx import Document
import plotly.express as px

# -------------------- Configurações Iniciais --------------------
st.set_page_config(page_title="Sistema Jurídico - Fernanda Freitas", layout="wide")
load_dotenv()

# Configuração da API DeepSeek e do Google Apps Script
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# -------------------- Usuários Persistidos --------------------
USUARIOS_FIXOS = {
    "dono": {
        "username": "dono",
        "senha": "dono123",
        "papel": "owner",
        "escritorio": "Global",
        "area": "Todas"
    },
    "gestor1": {
        "username": "gestor1",
        "senha": "gestor123",
        "papel": "manager",
        "escritorio": "Escritorio A",
        "area": "Todas"
    },
    "adv1": {
        "username": "adv1",
        "senha": "adv123",
        "papel": "lawyer",
        "escritorio": "Escritorio A",
        "area": "Criminal"
    }
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
def carregar_dados_da_planilha(tipo, debug=False, retries=3, timeout=30):
    """
    Faz requisição ao Google Apps Script para carregar dados de uma aba específica,
    tenta até `retries` vezes em caso de timeout, e retorna lista de dicts ou [].
    """
    for attempt in range(1, retries+1):
        try:
            response = requests.get(
                GAS_WEB_APP_URL,
                params={"tipo": tipo},
                timeout=timeout
            )
            response.raise_for_status()
            if debug:
                st.text(f"[DEBUG] Tentativa {attempt} — URL: {response.url}")
                st.text(f"[DEBUG] Resposta (primeiros 500 chars): {response.text[:500]}")
            return response.json()
        except requests.exceptions.ReadTimeout:
            if attempt < retries:
                st.warning(f"Timeout ao carregar '{tipo}', tentativa {attempt}/{retries}. Retentando em 2 s…")
                time.sleep(2)
                continue
            else:
                st.error(f"Timeout ao carregar dados ('{tipo}') após {retries} tentativas.")
                return []
        except Exception as e:
            st.error(f"Erro ao carregar dados ('{tipo}'): {e}")
            return []

def enviar_dados_para_planilha(tipo, dados):
    """
    Envia os dados para a aba especificada em 'tipo' via Google Apps Script.
    Retorna True se o envio foi bem-sucedido.
    """
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
    funcionarios = carregar_dados_da_planilha("Funcionario") or []
    users_dict = {}
    if not funcionarios:
        users_dict["dono"] = {"username": "dono", "senha": "dono123", "papel": "owner", "escritorio": "Global", "area": "Todas"}
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
    users = st.session_state.get("USERS", {})
    user = users.get(usuario)
    if user and user["senha"] == senha:
        return user
    return None

def calcular_status_processo(data_prazo, houve_movimentacao, encerrado=False):
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
        encerrado = processo.get("encerrado", False)
        status = calcular_status_processo(prazo, processo.get("houve_movimentacao", False), encerrado=encerrado)
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

def get_dataframe_with_cols(data, columns):
    if isinstance(data, dict):
        data = [data]
    df = pd.DataFrame(data)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]

def buscar_processo_por_numero(numero, processos):
    """
    Retorna o dict do processo cujo 'numero' coincide com o informado,
    ou None se não encontrar.
    """
    for p in processos:
        if p.get("numero") == numero:
            return p
    return None


##############################
# Interface Principal
##############################
def main():
    st.title("Sistema Jurídico - Fernanda Freitas")
    
    # 1) carrega apenas os funcionários da planilha
    usuarios_planilha = carregar_usuarios_da_planilha()

    # 2) mescla com os usuários fixos, sem removê‑los
    st.session_state.USERS = USUARIOS_FIXOS.copy()
    st.session_state.USERS.update(usuarios_planilha)
    
    # Carrega os dados de cada aba
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HISTORICO_PETICOES = carregar_dados_da_planilha("Historico_Peticao")
    if not isinstance(HISTORICO_PETICOES, list):
        HISTORICO_PETICOES = []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []
    LEADS = carregar_dados_da_planilha("Lead") or []
    LEADS = LEADS if isinstance(LEADS, list) else [LEADS]
    
    #####################
    # Sidebar: Login e Logout
    #####################
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
    
    #####################
    # Interface: Se o usuário está logado
    #####################
    if "usuario" in st.session_state:
        papel = st.session_state.papel
        escritorio_usuario = st.session_state.dados_usuario.get("escritorio", "Global")
        area_usuario = st.session_state.dados_usuario.get("area", "Todas")
        st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")
        area_fixa = area_usuario if (area_usuario and area_usuario != "Todas") else None
        
        # Menu Principal (incluindo "Gestão de Leads")
        opcoes = ["Dashboard", "Clientes", "Processos", "Históricos", "Gerenciar Funcionários"]
        if papel == "owner":
            opcoes.extend(["Gerenciar Escritórios", "Gerenciar Permissões"])
        elif papel == "manager":
            opcoes.extend(["Gerenciar Funcionários"])
        escolha = st.sidebar.selectbox("Menu", opcoes)
        
        #######################################
        # Dashboard
        #######################################
        if escolha == "Dashboard":
            st.subheader("📋 Painel de Controle de Processos")
            with st.expander("🔍 Filtros", expanded=True):
                col1, col2, col3 = st.columns(3)
                filtro_area = area_fixa if area_fixa else st.selectbox(
                    "Área",
                    ["Todas"] + sorted({p["area"] for p in PROCESSOS})
                )
                filtro_status = st.selectbox(
                    "Status",
                    ["Todos", "🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado", "⚫ Encerrado"]
                )
                filtro_escritorio = st.selectbox(
                    "Escritório",
                    ["Todos"] + sorted({p["escritorio"] for p in PROCESSOS})
                )

            # aplica filtros
            processos_visiveis = PROCESSOS.copy()
            if area_fixa:
                processos_visiveis = [p for p in processos_visiveis if p["area"] == area_fixa]
            elif filtro_area != "Todas":
                processos_visiveis = [p for p in processos_visiveis if p["area"] == filtro_area]
            if filtro_status != "Todos":
                if filtro_status == "⚫ Encerrado":
                    processos_visiveis = [p for p in processos_visiveis if p.get("encerrado", False)]
                else:
                    processos_visiveis = [
                        p for p in processos_visiveis
                        if calcular_status_processo(
                            converter_data(p.get("prazo")),
                            p.get("houve_movimentacao", False),
                            p.get("encerrado", False)
                        ) == filtro_status
                    ]
            if filtro_escritorio != "Todos":
                processos_visiveis = [p for p in processos_visiveis if p["escritorio"] == filtro_escritorio]

            # métricas
            st.subheader("📊 Visão Geral")
            total = len(processos_visiveis)
            atrasados = len([p for p in processos_visiveis
                             if calcular_status_processo(
                                 converter_data(p.get("prazo")),
                                 p.get("houve_movimentacao", False),
                                 p.get("encerrado", False)
                             ) == "🔴 Atrasado"])
            atencao = len([p for p in processos_visiveis
                           if calcular_status_processo(
                               converter_data(p.get("prazo")),
                               p.get("houve_movimentacao", False),
                               p.get("encerrado", False)
                           ) == "🟡 Atenção"])
            movimentados = len([p for p in processos_visiveis if p.get("houve_movimentacao", False)])
            encerrados = len([p for p in processos_visiveis if p.get("encerrado", False)])
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Total", total)
            c2.metric("Atrasados", atrasados)
            c3.metric("Atenção", atencao)
            c4.metric("Movimentados", movimentados)
            c5.metric("Encerrados", encerrados)

            # lista de processos
            st.subheader("📋 Lista de Processos")
            if processos_visiveis:
                cols = ["numero", "cliente", "area", "prazo", "responsavel", "link_material"]
                df_proc = get_dataframe_with_cols(processos_visiveis, cols)
                df_proc["Status"] = df_proc.apply(
                    lambda r: calcular_status_processo(
                        converter_data(r["prazo"]),
                        r.get("houve_movimentacao", False),
                        r.get("encerrado", False)
                    ), axis=1
                )
                # ordena pela ordem lógica de status
                ordem = {"🔴 Atrasado": 0, "🟡 Atenção": 1, "🟢 Normal": 2, "🔵 Movimentado": 3, "⚫ Encerrado": 4}
                df_proc["ord"] = df_proc["Status"].map(ordem)
                df_proc = df_proc.sort_values("ord").drop("ord", axis=1)

                # transform link em markdown clicável
                df_proc["link_material"] = df_proc["link_material"].apply(
                    lambda x: f"[Abrir Material]({x})" if x else ""
                )
                st.dataframe(df_proc)
            else:
                st.info("Nenhum processo encontrado com os filtros aplicados")

            # ===========================
            # ✏️ Editar / Excluir Processo
            # ===========================
            processo_alvo = None
            col_edi, col_bus = st.columns([3, 1])
            with col_edi:
                num_proc_edit = st.text_input("Número do Processo para editar/excluir")
            with col_bus:
                if st.button("🔍 Buscar Processo"):
                    encontrado = buscar_processo_por_numero(num_proc_edit, PROCESSOS)
                    if encontrado:
                        processo_alvo = encontrado
                        st.session_state["processo_alvo"] = encontrado
                    else:
                        st.warning("Processo não encontrado.")

            if "processo_alvo" in st.session_state:
                processo_alvo = st.session_state["processo_alvo"]

            if processo_alvo:
                st.write("### Editando Processo:", processo_alvo["numero"])
                novo_cliente   = st.text_input("Cliente", value=processo_alvo.get("cliente", ""))
                nova_descricao = st.text_area("Descrição", value=processo_alvo.get("descricao", ""))
                opcs_status    = ["🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado", "⚫ Encerrado"]
                try:
                    idx = opcs_status.index(
                        calcular_status_processo(
                            converter_data(processo_alvo.get("prazo")),
                            processo_alvo.get("houve_movimentacao", False),
                            processo_alvo.get("encerrado", False)
                        )
                    )
                except ValueError:
                    idx = 2
                novo_status = st.selectbox("Status", opcs_status, index=idx)
                novo_link   = st.text_input(
                    "Link do Material Complementar (opcional)",
                    value=processo_alvo.get("link_material", "")
                )

                e1, e2 = st.columns(2)
                with e1:
                    if st.button("Atualizar Processo"):
                        dados_atual = {
                            "cliente": novo_cliente,
                            "descricao": nova_descricao,
                            "status_manual": novo_status,
                            "link_material": novo_link
                        }
                        if atualizar_processo(processo_alvo["numero"], dados_atual):
                            st.success("Processo atualizado com sucesso!")
                            st.session_state.pop("processo_alvo", None)
                        else:
                            st.error("Falha ao atualizar processo.")
                with e2:
                    if st.button("Excluir Processo"):
                        if excluir_processo(processo_alvo["numero"]):
                            st.success("Processo excluído com sucesso!")
                            st.session_state.pop("processo_alvo", None)
                            PROCESSOS[:] = [
                                p for p in PROCESSOS if p["numero"] != processo_alvo["numero"]
                            ]
                        else:
                            st.error("Falha ao excluir processo.")

            elif num_proc_edit:
                st.warning("Processo não encontrado.")
                
                # 3) recupera de session_state caso setado
                if "processo_alvo" in st.session_state:
                    processo_alvo = st.session_state["processo_alvo"]
                
                # 4) só renderiza o form se realmente houver um processo alvo
                if processo_alvo:
                    st.write("Edite os campos abaixo:")
                    # preenche campos com dados atuais
                    novo_cliente    = st.text_input("Cliente", default_value=processo_alvo.get("cliente",""))
                    nova_descricao  = st.text_area("Descrição", value=processo_alvo.get("descricao",""))
                    opcoes_status   = ["🔴 Atrasado","🟡 Atenção","🟢 Normal","🔵 Movimentado","⚫ Encerrado"]
                    # calcula índice inicial de status
                    try:
                        status_atual = calcular_status_processo(
                            converter_data(processo_alvo.get("prazo")),
                            processo_alvo.get("houve_movimentacao", False),
                            processo_alvo.get("encerrado", False)
                        )
                        idx = opcoes_status.index(status_atual)
                    except ValueError:
                        idx = 2
                    novo_status     = st.selectbox("Status", opcoes_status, index=idx)
                    novo_link       = st.text_input(
                        "Link do Material Complementar (opcional)",
                        value=processo_alvo.get("link_material","")
                    )
                
                    col_ed, col_exc = st.columns(2)
                    with col_ed:
                        if st.button("Atualizar Processo"):
                            atualizacoes = {
                                "cliente": processo_alvo.get("cliente","") if not novo_cliente else novo_cliente,
                                "descricao": nova_descricao,
                                "status_manual": novo_status,
                                "link_material": novo_link
                            }
                            if atualizar_processo(processo_alvo.get("numero"), atualizacoes):
                                st.success("Processo atualizado com sucesso!")
                                # limpa o alvo para nova busca
                                st.session_state.pop("processo_alvo", None)
                            else:
                                st.error("Falha ao atualizar processo.")
                    with col_exc:
                        if st.button("Excluir Processo"):
                            if excluir_processo(processo_alvo.get("numero")):
                                st.success("Processo excluído com sucesso!")
                                # remove tanto do session_state quanto da lista local
                                st.session_state.pop("processo_alvo", None)
                                PROCESSOS[:] = [p for p in PROCESSOS if p.get("numero") != processo_alvo.get("numero")]
                            else:
                                st.error("Falha ao excluir processo.")

                else:
                    st.warning("Processo não encontrado.")
        
        # ------------------ Clientes ------------------ #
        elif escolha == "Clientes":
            st.subheader("👥 Cadastro de Clientes")
            with st.form("form_cliente"):
                nome       = st.text_input("Nome Completo*", key="nome_cliente")
                email      = st.text_input("E-mail*")
                telefone   = st.text_input("Telefone*")
                aniversario = st.date_input("Data de Nascimento")
                endereco   = st.text_input("Endereço*", placeholder="Rua, número, bairro, cidade, CEP")
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

            st.subheader("Lista de Clientes")
            if CLIENTES:
                df_cliente = get_dataframe_with_cols(
                    CLIENTES,
                    ["nome", "email", "telefone", "aniversario", "endereco", "cadastro"]
                )
                st.dataframe(df_cliente)

                col_export1, col_export2 = st.columns(2)
                with col_export1:
                    if st.button("Exportar Clientes (TXT)"):
                        txt = "\n".join([
                            f'{c.get("nome","")} | {c.get("email","")} | {c.get("telefone","")}'
                            for c in CLIENTES
                        ])
                        st.download_button("Baixar TXT", txt, file_name="clientes.txt")

                with col_export2:
                    if st.button("Exportar Clientes (PDF)"):
                        texto_pdf = "\n".join([
                            f'{c.get("nome","")} | {c.get("email","")} | {c.get("telefone","")}'
                            for c in CLIENTES
                        ])
                        pdf_file = exportar_pdf(texto_pdf, nome_arquivo="clientes")
                        with open(pdf_file, "rb") as f:
                            st.download_button("Baixar PDF", f, file_name=pdf_file)
            else:
                st.info("Nenhum cliente cadastrado ainda")                  
        
        # ------------------ Processos ------------------ #
        elif escolha == "Processos":
            st.subheader("📄 Cadastro de Processos")
            with st.form("form_processo"):
            st.subheader("Lista de Processos Cadastrados")        
            if PROCESSOS:
                # DataFrame + status
                cols_proc = ["numero", "cliente", "area", "prazo", "responsavel", "link_material"]
                df_proc = get_dataframe_with_cols(PROCESSOS, cols_proc)
                df_proc["Status"] = df_proc.apply(
                    lambda r: calcular_status_processo(
                        converter_data(r.get("prazo")),
                        r.get("houve_movimentacao", False),
                        r.get("encerrado", False)
                    ), axis=1
                )
                # ordenar e renderizar
                st.dataframe(df_proc)
        
                # Exportação TXT / PDF
                col_export1, col_export2 = st.columns(2)
                with col_export1:
                    if st.button("Exportar Processos (TXT)"):
                        # ... seu código de export TXT ...
                with col_export2:
                    if st.button("Exportar Processos (PDF)"):
                        # ... seu código de export PDF ...
        
                # ====== Novo: Editar / Excluir Processo ======
                st.markdown("---")
                processo_alvo = None
                col1, col2 = st.columns([3,1])
                with col1:
                    num_edit = st.text_input("Número do processo para editar/excluir", key="edit_proc")
                with col2:
                    if st.button("🔍 Buscar", key="btn_buscar_proc"):
                        p = buscar_processo_por_numero(num_edit, PROCESSOS)
                        if p:
                            processo_alvo = p
                            st.session_state["proc_edit"] = p
                        else:
                            st.warning("Processo não encontrado.")
                if "proc_edit" in st.session_state:
                    processo_alvo = st.session_state["proc_edit"]
        
                if processo_alvo:
                    st.write(f"**Editando Processo:** {processo_alvo['numero']}")
                    novo_cli = st.text_input("Cliente", value=processo_alvo.get("cliente",""))
                    nova_desc = st.text_area("Descrição", value=processo_alvo.get("descricao",""))
                    opcs = ["🔴 Atrasado","🟡 Atenção","🟢 Normal","🔵 Movimentado","⚫ Encerrado"]
                    try:
                        idx0 = opcs.index(calcular_status_processo(
                            converter_data(processo_alvo.get("prazo")),
                            processo_alvo.get("houve_movimentacao",False),
                            processo_alvo.get("encerrado",False)))
                    except ValueError:
                        idx0 = 2
                    novo_stat = st.selectbox("Status", opcs, index=idx0)
                    novo_link = st.text_input("Link material (opcional)", value=processo_alvo.get("link_material",""))
        
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Atualizar Processo", key="btn_atualiza_proc"):
                            dados = {
                                "cliente": novo_cli,
                                "descricao": nova_desc,
                                "status_manual": novo_stat,
                                "link_material": novo_link
                            }
                            ok = atualizar_processo(processo_alvo["numero"], dados)
                            if ok:
                                st.success("Processo atualizado com sucesso!")
                                st.session_state.pop("proc_edit", None)
                            else:
                                st.error("Erro ao atualizar processo.")
                    with c2:
                        if st.button("Excluir Processo", key="btn_exclui_proc"):
                            ok = excluir_processo(processo_alvo["numero"])
                            if ok:
                                st.success("Processo excluído com sucesso!")
                                st.session_state.pop("proc_edit", None)
                                PROCESSOS[:] = [p for p in PROCESSOS if p["numero"]!=processo_alvo["numero"]]
                            else:
                                st.error("Erro ao excluir processo.")
            else:
                st.info("Nenhum processo cadastrado ainda")

        
        # ------------------ Históricos ------------------ #
        elif escolha == "Históricos":
            st.subheader("📜 Histórico de Processos + Consulta TJMG")
            num_proc = st.text_input("Digite o número do processo para consultar o histórico")
            if num_proc:
                historico_filtrado = [h for h in HISTORICO_PETICOES if h.get("numero") == num_proc]
                if historico_filtrado:
                    st.write(f"{len(historico_filtrado)} registro(s) encontrado(s) para o processo {num_proc}:")
                    for item in historico_filtrado:
                        with st.expander(f"{item['tipo']} - {item['data']} - {item.get('cliente_associado', '')}"):
                            st.write(f"**Responsável:** {item['responsavel']}")
                            st.write(f"**Escritório:** {item.get('escritorio', '')}")
                            st.text_area("Conteúdo", value=item.get("conteudo", ""), key=item["data"], disabled=True)
                else:
                    st.info("Nenhum histórico encontrado para esse processo.")
            st.write("**Consulta TJMG (iframe)**")
            iframe_html = """
<div style="overflow: auto; height:600px;">
  <iframe src="https://www.tjmg.jus.br/portal-tjmg/processos/andamento-processual/"
          style="width:100%; height:100%; border:none;"
          scrolling="yes">
  </iframe>
</div>
"""
            st.components.v1.html(iframe_html, height=600)
                       
        # ------------------ Gerenciar Funcionários ------------------ #
        elif escolha == "Gerenciar Funcionários":
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
                        novo_funcionario = {"nome": nome,
                                            "email": email,
                                            "telefone": telefone,
                                            "usuario": usuario_novo,
                                            "senha": senha_novo,
                                            "escritorio": escritorio,
                                            "area": area_atuacao,
                                            "papel": papel_func,
                                            "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                            "cadastrado_por": st.session_state.usuario}
                        if enviar_dados_para_planilha("Funcionario", novo_funcionario):
                            st.success("Funcionário cadastrado com sucesso!")
                            st.session_state.USERS = carregar_usuarios_da_planilha()
            st.subheader("Lista de Funcionários")
            if FUNCIONARIOS:
                funcionarios_visiveis = [f for f in FUNCIONARIOS if f.get("escritorio") == escritorio_usuario] if papel == "manager" else FUNCIONARIOS
                if funcionarios_visiveis:
                    df_func = get_dataframe_with_cols(funcionarios_visiveis, ["nome", "email", "telefone", "usuario", "papel", "escritorio", "area"])
                    st.dataframe(df_func)
                    col_export1, col_export2 = st.columns(2)
                    with col_export1:
                        if st.button("Exportar Funcionários (TXT)"):
                            txt = "\n".join([f'{f.get("nome","")} | {f.get("email","")} | {f.get("telefone","")}' for f in funcionarios_visiveis])
                            st.download_button("Baixar TXT", txt, file_name="funcionarios.txt")
                    with col_export2:
                        if st.button("Exportar Funcionários (PDF)"):
                            texto_pdf = "\n".join([f'{f.get("nome","")} | {f.get("email","")} | {f.get("telefone","")}' for f in funcionarios_visiveis])
                            pdf_file = exportar_pdf(texto_pdf, nome_arquivo="funcionarios")
                            with open(pdf_file, "rb") as f:
                                st.download_button("Baixar PDF", f, file_name=pdf_file)
                else:
                    st.info("Nenhum funcionário cadastrado para este escritório")
            else:
                st.info("Nenhum funcionário cadastrado ainda")
        
        # ------------------ Gerenciar Escritórios (Apenas Owner) ------------------ #
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
                            novo_escritorio = {"nome": nome,
                                               "endereco": endereco,
                                               "telefone": telefone,
                                               "email": email,
                                               "cnpj": cnpj,
                                               "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                               "responsavel": st.session_state.usuario,
                                               "responsavel_tecnico": responsavel_tecnico,
                                               "telefone_tecnico": telefone_tecnico,
                                               "email_tecnico": email_tecnico,
                                               "area_atuacao": ", ".join(area_atuacao)}
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
                            txt = "\n".join([f'{e.get("nome", "")} | {e.get("endereco", "")} | {e.get("telefone", "")}' for e in ESCRITORIOS])
                            st.download_button("Baixar TXT", txt, file_name="escritorios.txt")
                    with col_exp2:
                        if st.button("Exportar Escritórios (PDF)"):
                            txt_exp = "\n".join([f'{e.get("nome", "")} | {e.get("endereco", "")} | {e.get("telefone", "")}' for e in ESCRITORIOS])
                            pdf_file = exportar_pdf(txt_exp, nome_arquivo="escritorios")
                            with open(pdf_file, "rb") as f:
                                st.download_button("Baixar PDF", f, file_name=pdf_file)
                else:
                    st.info("Nenhum escritório cadastrado ainda")
            with tab3:
                st.subheader("Administradores de Escritórios")
                st.info("Funcionalidade em desenvolvimento.")
        
        # ------------------ Gerenciar Permissões (Apenas Owner) ------------------ #
        elif escolha == "Gerenciar Permissões" and papel == "owner":
            st.subheader("🔧 Gerenciar Permissões de Funcionários")
            st.info("Configure as áreas de atuação do funcionário.")
            if FUNCIONARIOS:
                df_func = pd.DataFrame(FUNCIONARIOS)
                st.dataframe(df_func)
                funcionario_selecionado = st.selectbox("Funcionário", df_func["nome"].tolist())
                novas_areas = st.multiselect(
                    "Áreas Permitidas",
                    ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"]
                )
                if st.button("Atualizar Permissões"):
                    atualizado = False
                    # renomeei as variáveis para evitar shadowing
                    for idx, funcionario_item in enumerate(FUNCIONARIOS):
                        if funcionario_item.get("nome") == funcionario_selecionado:
                            FUNCIONARIOS[idx]["area"] = ", ".join(novas_areas)
                            atualizado = True
                            for key, usuario_item in st.session_state.USERS.items():
                                if usuario_item.get("username") == funcionario_item.get("usuario"):
                                    st.session_state.USERS[key]["area"] = ", ".join(novas_areas)
                    if atualizado:
                        payload = {
                            "nome": funcionario_selecionado,
                            "area": ", ".join(novas_areas),
                            "atualizar": True
                        }
                        sucesso = enviar_dados_para_planilha("Funcionario", payload)
                        if sucesso:
                            st.success("Permissões atualizadas com sucesso!")
                        else:
                            st.error("Falha ao atualizar permissões.")
            else:
                st.info("Nenhum funcionário cadastrado.")
    
    else:
        st.info("Por favor, faça login para acessar o sistema.")

if __name__ == '__main__':
    main()
