import streamlit as st
import datetime
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
st.set_page_config(page_title="Sistema Jurídico", layout="wide")
load_dotenv()

# Configuração da API DeepSeek e do Google Apps Script
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-...")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/.../exec"

# -------------------- Usuários Persistidos --------------------
if "USERS" not in st.session_state:
    st.session_state.USERS = {
        "dono": {"username": "dono", "senha": "dono123", "papel": "owner"},
        "gestor1": {"username": "gestor1", "senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A", "area": "Todas"},
        "adv1":   {"username": "adv1",   "senha": "adv123",   "papel": "lawyer",   "escritorio": "Escritorio A", "area": "Criminal"}
    }

# -------------------- Funções Auxiliares --------------------
def converter_data(data_str):
    if not data_str:
        return datetime.date.today()
    try:
        data_str = data_str.replace("Z","")
        if "T" in data_str:
            return datetime.datetime.fromisoformat(data_str).date()
        return datetime.date.fromisoformat(data_str)
    except:
        return datetime.date.today()

@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados_da_planilha(tipo, debug=False):
    try:
        response = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo}, timeout=10)
        response.raise_for_status()
        if debug:
            st.text(f"URL: {response.url}")
            st.text(response.text[:500])
        return response.json()
    except Exception as e:
        st.error(f"Erro ao carregar {tipo}: {e}")
        return []

def enviar_dados_para_planilha(tipo, dados):
    try:
        payload = {"tipo": tipo, **dados}
        with httpx.Client(timeout=10, follow_redirects=True) as cli:
            r = cli.post(GAS_WEB_APP_URL, json=payload)
        return r.text.strip() == "OK"
    except Exception as e:
        st.error(f"Erro ao enviar {tipo}: {e}")
        return False

def carregar_usuarios_da_planilha():
    funcs = carregar_dados_da_planilha("Funcionario") or []
    users = {}
    if not funcs:
        users["dono"] = {"username":"dono","senha":"dono123","papel":"owner","escritorio":"Global","area":"Todas"}
        return users
    for f in funcs:
        u = f.get("usuario")
        if not u: continue
        users[u] = {
            "username": u,
            "senha": f.get("senha",""),
            "papel": f.get("papel","assistant"),
            "escritorio": f.get("escritorio","Global"),
            "area": f.get("area","Todas")
        }
    return users

def login(usuario, senha):
    user = st.session_state.USERS.get(usuario)
    if user and user["senha"] == senha:
        return user
    return None

def calcular_status_processo(data_prazo, mov, encerrado=False):
    if encerrado: return "⚫ Encerrado"
    hoje = datetime.date.today()
    dias = (data_prazo - hoje).days
    if mov:        return "🔵 Movimentado"
    if dias < 0:   return "🔴 Atrasado"
    if dias <=10:  return "🟡 Atenção"
    return "🟢 Normal"

def exportar_pdf(texto, nome_arquivo="relatorio"):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=12)
    pdf.multi_cell(0,10, texto)
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def get_dataframe_with_cols(data, cols):
    if isinstance(data, dict): data = [data]
    df = pd.DataFrame(data)
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df[cols]

##############################
# Interface Principal
##############################
def main():
    st.title("Sistema Jurídico")
    # atualiza usuários
    st.session_state.USERS = carregar_usuarios_da_planilha()

    # carrega abas
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HIST_PETICOES = carregar_dados_da_planilha("Historico_Peticao") or []
    if not isinstance(HIST_PETICOES, list): HIST_PETICOES = []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []

    # Sidebar: login
    with st.sidebar:
        st.header("🔐 Login")
        u = st.text_input("Usuário")
        s = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            usr = login(u,s)
            if usr:
                st.session_state.usuario = u
                st.session_state.papel   = usr["papel"]
                st.session_state.dados_usuario = usr
                st.success("Login ok!")
            else:
                st.error("Credenciais inválidas")
    if "usuario" in st.session_state:
        if st.sidebar.button("Sair"):
            for k in ["usuario","papel","dados_usuario"]:
                st.session_state.pop(k,None)
            st.sidebar.success("Você saiu")
            st.experimental_rerun()

    # após login
    if "usuario" not in st.session_state:
        st.info("Faça login para acessar")
        return

    papel = st.session_state.papel
    esc_user = st.session_state.dados_usuario.get("escritorio","Global")
    area_user= st.session_state.dados_usuario.get("area","Todas")
    st.sidebar.success(f"{st.session_state.usuario} ({papel})")

    # menu
    ops = ["Dashboard", "Clientes", "Processos", "Históricos", "Relatórios", "Gerenciar Funcionários"]
    if papel=="owner": ops += ["Gerenciar Escritórios", "Gerenciar Permissões"]
    escolha = st.sidebar.selectbox("Menu", ops)

    # Dashboard
    if escolha=="Dashboard":
        st.subheader("📋 Painel de Controle")
        # implementação idêntica à anterior...
        pass

    # ------------------ Clientes ------------------
    elif escolha == "Clientes":
        st.subheader("👥 Cadastro de Clientes")
        with st.form("form_cliente", clear_on_submit=True):
            nome         = st.text_input("Nome Completo*", key="nome_cliente")
            email        = st.text_input("E-mail*")
            telefone     = st.text_input("Telefone*")
            aniversario  = st.date_input("Data de Nascimento")
            endereco     = st.text_input("Endereço*", placeholder="Rua, número, bairro, cidade, CEP")
            escritorio   = st.selectbox("Escritório", [e["nome"] for e in ESCRITORIOS] + ["Outro"])
            tipo_cliente = st.selectbox("Tipo de Cliente*", ["Ativo", "Inativo", "Lead"])
            observacoes  = st.text_area("Observações")
            if st.form_submit_button("Salvar Cliente"):
                if not (nome and email and telefone and endereco):
                    st.warning("Campos obrigatórios não preenchidos!")
                else:
                    novo_cliente = {
                        "nome": nome,
                        "email": email,
                        "telefone": telefone,
                        "aniversario": aniversario.strftime("%Y-%m-%d"),
                        "endereco": endereco,
                        "escritorio": escritorio,
                        "tipo_cliente": tipo_cliente,
                        "observacoes": observacoes,
                        "cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "responsavel": st.session_state.usuario
                    }
                    if enviar_dados_para_planilha("Cliente", novo_cliente):
                        CLIENTES.append(novo_cliente)
                        st.success("Cliente cadastrado com sucesso!")
    
        st.subheader("Lista de Clientes")
        if CLIENTES:
            df_cliente = get_dataframe_with_cols(
                CLIENTES,
                ["nome", "email", "telefone", "endereco", "tipo_cliente", "cadastro"]
            )
            st.dataframe(df_cliente)
    
            # monta o texto de exportação corretamente
            export_txt = "\n".join([
                f"{c['nome']} | {c['email']} | {c['telefone']} | {c['tipo_cliente']}"
                for c in CLIENTES
            ])
    
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📄 Baixar Clientes (TXT)",
                    data=export_txt,
                    file_name="clientes.txt",
                    mime="text/plain"
                )
            with col2:
                pdf_file = exportar_pdf(export_txt, nome_arquivo="clientes")
                with open(pdf_file, "rb") as f:
                    st.download_button(
                        "📄 Baixar Clientes (PDF)",
                        data=f,
                        file_name="clientes.pdf",
                        mime="application/pdf"
                    )
        else:
            st.info("Nenhum cliente cadastrado ainda")

    # ------------------ Processos ------------------
    elif escolha=="Processos":
        st.subheader("📄 Cadastro de Processos")
        with st.form("form_processo"):
            cliente_nome      = st.text_input("Cliente*")
            numero_processo   = st.text_input("Número do Processo*")
            tipo_contrato     = st.selectbox("Tipo de Contrato*", ["Fixo","Por Ato","Contingência"])
            descricao         = st.text_area("Descrição*")
            col1,col2         = st.columns(2)
            with col1:
                valor_total     = st.number_input("Valor Total (R$)*",min_value=0.0,format="%.2f")
            with col2:
                valor_movimentado = st.number_input("Valor Movimentado (R$)",min_value=0.0,format="%.2f")
            prazo_inicial     = st.date_input("Prazo Inicial*", datetime.date.today())
            prazo_final       = st.date_input("Prazo Final*", datetime.date.today()+datetime.timedelta(days=30))
            houve_mov         = st.checkbox("Houve movimentação?")
            area              = st.selectbox("Área*",["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
            if area_user!="Todas":
                st.info(f"Área fixada: {area_user}")
                area = area_user
            link_material     = st.text_input("Link Material (opcional)")
            encerrado         = st.checkbox("Processo Encerrado?")
            if st.form_submit_button("Salvar Processo"):
                if not (cliente_nome and numero_processo and descricao):
                    st.warning("Preencha campos obrigatórios!")
                else:
                    novo = {
                        "cliente":cliente_nome,
                        "numero":numero_processo,
                        "contrato":tipo_contrato,
                        "descricao":descricao,
                        "valor_total":valor_total,
                        "valor_movimentado":valor_movimentado,
                        "prazo_inicial":prazo_inicial.strftime("%Y-%m-%d"),
                        "prazo":prazo_final.strftime("%Y-%m-%d"),
                        "houve_movimentacao":houve_mov,
                        "encerrado":encerrado,
                        "escritorio":st.session_state.dados_usuario.get("escritorio","Global"),
                        "area":area,
                        "responsavel":st.session_state.usuario,
                        "link_material":link_material,
                        "data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    if enviar_dados_para_planilha("Processo", novo):
                        PROCESSOS.append(novo)
                        st.success("Processo cadastrado com sucesso!")

        st.subheader("Lista de Processos")
        if PROCESSOS:
            cols = ["numero","cliente","area","prazo","responsavel","link_material"]
            dfp = get_dataframe_with_cols(PROCESSOS, cols)
            dfp["Status"] = dfp.apply(lambda r: calcular_status_processo(
                converter_data(r["prazo"]), r.get("houve_movimentacao",False), r.get("encerrado",False)
            ), axis=1)
            st.dataframe(dfp)
        else:
            st.info("Nenhum processo cadastrado")

    # ------------------ Históricos ------------------
    elif escolha=="Históricos":
        st.subheader("📜 Histórico + Consulta TJMG")
        num = st.text_input("Número do processo")
        if num:
            hist = [h for h in HIST_PETICOES if h.get("numero")==num]
            if hist:
                st.write(f"{len(hist)} registros:")
                for it in hist:
                    with st.expander(f"{it['tipo']} - {it['data']}"):
                        st.write(f"Responsável: {it['responsavel']}")
                        st.write(f"Escritório: {it.get('escritorio','')}")
                        st.text_area("Conteúdo", value=it.get("conteudo",""), disabled=True)
            else:
                st.info("Nenhum histórico encontrado.")
        st.write("**Consulta TJMG**")
        iframe = """
<div style="overflow:auto;height:600px">
  <iframe src="https://www.tjmg.jus.br/portal-tjmg/processos/andamento-processual/" 
          style="width:100%;height:100%;border:none;" scrolling="yes"></iframe>
</div>
"""
        st.components.v1.html(iframe, height=600)
        
     # ------------------ Relatórios ------------------ #
     elif escolha == "Relatórios":
            st.subheader("📊 Relatórios Personalizados")
            with st.expander("🔍 Filtros Avançados", expanded=True):
                with st.form("form_filtros"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        # Inclui a opção "Leads"
                        tipo_relatorio = st.selectbox("Tipo de Relatório*", ["Processos", "Escritórios", "Leads"])
                        if tipo_relatorio == "Processos":
                            if area_usuario and area_usuario != "Todas":
                                area_filtro = area_usuario
                                st.info(f"Filtrando pela área: {area_usuario}")
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
                        formato_exportacao = st.selectbox("Formato de Exportação", ["PDF", "DOCX", "CSV", "TXT"])
                    if st.form_submit_button("Aplicar Filtros"):
                        if tipo_relatorio == "Processos":
                            filtros = {"area": area_filtro, "escritorio": escritorio_filtro, 
                                       "responsavel": responsavel_filtro, "data_inicio": data_inicio, "data_fim": data_fim}
                            dados_filtrados = aplicar_filtros(PROCESSOS, filtros)
                            if status_filtro != "Todos":
                                if status_filtro == "⚫ Encerrado":
                                    dados_filtrados = [p for p in dados_filtrados if p.get("encerrado", False)]
                                else:
                                    dados_filtrados = [p for p in dados_filtrados if calcular_status_processo(
                                        converter_data(p.get("prazo")),
                                        p.get("houve_movimentacao", False),
                                        p.get("encerrado", False)) == status_filtro]
                            st.session_state.dados_relatorio = dados_filtrados
                            st.session_state.tipo_relatorio = "Processos"
                        elif tipo_relatorio == "Escritórios":
                            filtros = {"data_inicio": data_inicio, "data_fim": data_fim}
                            dados_filtrados = aplicar_filtros(ESCRITORIOS, filtros)
                            st.session_state.dados_relatorio = dados_filtrados
                            st.session_state.tipo_relatorio = "Escritórios"
                        else:  # Leads
                            st.session_state.dados_relatorio = LEADS
                            st.session_state.tipo_relatorio = "Leads"
            if "dados_relatorio" in st.session_state and st.session_state.dados_relatorio:
                st.write(f"{st.session_state.tipo_relatorio} encontrados: {len(st.session_state.dados_relatorio)}")
                if st.button(f"Exportar Relatório ({formato_exportacao})"):
                    if formato_exportacao == "PDF":
                        if st.session_state.tipo_relatorio == "Processos":
                            arquivo = gerar_relatorio_pdf(st.session_state.dados_relatorio)
                        elif st.session_state.tipo_relatorio == "Leads":
                            # Corrigindo as chaves para os Leads: usa "contato" e "email"
                            texto = "\n".join([f"Nome: {l.get('nome','')}, Contato: {l.get('contato','')}, E-mail: {l.get('email','')}, Data de Aniversário: {l.get('data_aniversario','')}"
                                                for l in st.session_state.dados_relatorio])
                            arquivo = exportar_pdf(texto, nome_arquivo="relatorio_leads")
                        else:
                            arquivo = exportar_pdf(str(st.session_state.dados_relatorio))
                        with open(arquivo, "rb") as f:
                            st.download_button("Baixar PDF", f, file_name=arquivo)
                    elif formato_exportacao == "DOCX":
                        if st.session_state.tipo_relatorio == "Processos":
                            texto = "\n".join([f"{p['numero']} - {p['cliente']}" for p in st.session_state.dados_relatorio])
                        elif st.session_state.tipo_relatorio == "Leads":
                            texto = "\n".join([f"Nome: {l.get('nome','')}, Contato: {l.get('contato','')}, E-mail: {l.get('email','')}, Data de Aniversário: {l.get('data_aniversario','')}"
                                                for l in st.session_state.dados_relatorio])
                        else:
                            texto = str(st.session_state.dados_relatorio)
                        arquivo = exportar_docx(texto)
                        with open(arquivo, "rb") as f:
                            st.download_button("Baixar DOCX", f, file_name=arquivo)
                    elif formato_exportacao == "CSV":
                        df_export = pd.DataFrame(st.session_state.dados_relatorio)
                        csv_bytes = df_export.to_csv(index=False).encode("utf-8")
                        st.download_button("Baixar CSV", data=csv_bytes, file_name=f"relatorio_{datetime.datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
                        st.dataframe(st.session_state.dados_relatorio)
                    elif formato_exportacao == "TXT":
                        if st.session_state.tipo_relatorio == "Leads":
                            leads_data = st.session_state.dados_relatorio
                            if not isinstance(leads_data, list):
                                leads_data = [leads_data]
                            texto = "\n".join([f"Nome: {l.get('nome','')}, Contato: {l.get('contato','')}, E-mail: {l.get('email','')}, Data de Aniversário: {l.get('data_aniversario','')}"
                                                for l in leads_data])
                            st.download_button("Baixar TXT", data=texto, file_name="relatorio_leads.txt", mime="text/plain")
                        else:
                            st.info("A opção TXT está disponível apenas para o relatório de Leads.")
                    else:
                        st.info("Nenhum dado encontrado com os filtros aplicados")      
        
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
                novas_areas = st.multiselect("Áreas Permitidas", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                if st.button("Atualizar Permissões"):
                    atualizado = False
                    for idx, func in enumerate(FUNCIONARIOS):
                        if func.get("nome") == funcionario_selecionado:
                            FUNCIONARIOS[idx]["area"] = ", ".join(novas_areas)
                            atualizado = True
                            for key, user in st.session_state.USERS.items():
                                if user.get("username") == func.get("usuario"):
                                    st.session_state.USERS[key]["area"] = ", ".join(novas_areas)
                    if atualizado:
                        if enviar_dados_para_planilha("Funcionario", {"nome": funcionario_selecionado, "area": ", ".join(novas_areas), "atualizar": True}):
                            st.success("Permissões atualizadas com sucesso!")
                        else:
                            st.error("Falha ao atualizar permissões.")
            else:
                st.info("Nenhum funcionário cadastrado.")
    
    else:
        st.info("Por favor, faça login para acessar o sistema.")

if __name__ == '__main__':
    main()
