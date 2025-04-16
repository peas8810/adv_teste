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
        "adv1": {"username": "adv1", "senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Criminal"},
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
    except:
        return datetime.date.today()

@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados_da_planilha(tipo):
    try:
        resp = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo}, timeout=10)
        resp.raise_for_status()
        return resp.json() if resp.text else []
    except Exception as e:
        st.error(f"Erro ao carregar {tipo}: {e}")
        return []

def enviar_dados_para_planilha(tipo, dados):
    try:
        payload = {"tipo": tipo, **dados}
        with httpx.Client(timeout=10) as client:
            r = client.post(GAS_WEB_APP_URL, json=payload)
        return r.text.strip() == "OK"
    except Exception as e:
        st.error(f"Erro ao enviar {tipo}: {e}")
        return False

def login(usuario, senha):
    user = st.session_state.USERS.get(usuario)
    if user and user["senha"] == senha:
        return user
    return None

def exportar_pdf(texto, nome_arquivo="relatorio"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for linha in texto.split("\n"):
        pdf.multi_cell(0, 8, linha)
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def get_dataframe_with_cols(data, cols):
    df = pd.DataFrame(data or [])
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols]

##############################
# Interface Principal
##############################
def main():
    st.title("Sistema Jurídico")
    # recarrega usuários a partir da planilha
    st.session_state.USERS = {**st.session_state.USERS, **{u["usuario"]:{
        "username":u["usuario"],"senha":u.get("senha",""),"papel":u.get("papel","assistant"),
        "escritorio":u.get("escritorio","Global"),"area":u.get("area","Todas")
    } for u in carregar_dados_da_planilha("Funcionario")}}

    CLIENTES = carregar_dados_da_planilha("Cliente")
    PROCESSOS = carregar_dados_da_planilha("Processo")
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio")
    HISTORICO = carregar_dados_da_planilha("Historico_Peticao")
    LEADS = carregar_dados_da_planilha("Lead")
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario")

    # Sidebar: login/logout
    with st.sidebar:
        if "usuario" not in st.session_state:
            st.header("🔐 Login")
            u = st.text_input("Usuário")
            s = st.text_input("Senha", type="password")
            if st.button("Entrar"):
                user = login(u, s)
                if user:
                    st.session_state.usuario = u
                    st.session_state.papel = user["papel"]
                    st.success("Login realizado!")
                    st.experimental_rerun()
                else:
                    st.error("Credenciais inválidas")
        else:
            st.sidebar.success(f"Olá, {st.session_state.usuario}")
            if st.sidebar.button("Sair"):
                for k in ("usuario","papel"): st.session_state.pop(k, None)
                st.experimental_rerun()

    if "usuario" not in st.session_state:
        st.info("Faça login para continuar.")
        return

    papel = st.session_state.papel
    opcoes = ["Dashboard", "Clientes", "Gestão de Leads", "Processos", "Históricos", "Gerenciar Funcionários"]
    if papel == "owner":
        opcoes += ["Gerenciar Escritórios", "Gerenciar Permissões"]
    escolha = st.sidebar.selectbox("Menu", opcoes)

    # ------------------ Dashboard ------------------ #
    if escolha == "Dashboard":
        st.subheader("📊 Painel de Controle")
        st.write("Sem alterações nesta aba.")

    # ------------------ Clientes ------------------ #
    elif escolha == "Clientes":
        st.subheader("👥 Cadastro de Clientes")
        with st.form("form_cliente"):
            nome = st.text_input("Nome Completo*", key="nome_cliente")
            email = st.text_input("E-mail*")
            tel = st.text_input("Telefone*")
            aniversario = st.date_input("Data de Nascimento")
            endereco = st.text_input("Endereço*")
            observ = st.text_area("Observações")
            status = st.selectbox("Status*", ["Ativo", "Inativo", "Lead"])
            if st.form_submit_button("Salvar Cliente"):
                if not (nome and email and tel and endereco):
                    st.warning("Preencha todos os campos obrigatórios!")
                else:
                    novo = {
                        "nome": nome, "email": email, "telefone": tel,
                        "aniversario": aniversario.strftime("%Y-%m-%d"),
                        "endereco": endereco, "observacoes": observ,
                        "status": status,
                        "cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "responsavel": st.session_state.usuario
                    }
                    if enviar_dados_para_planilha("Cliente", novo):
                        CLIENTES.append(novo)
                        st.success("Cliente cadastrado!")

        st.subheader("📋 Lista de Clientes")
        status_filter = st.selectbox("Filtrar por Status", ["Todos", "Ativo", "Inativo", "Lead"])
        clientes_vis = CLIENTES if status_filter=="Todos" else [c for c in CLIENTES if c.get("status")==status_filter]
        if clientes_vis:
            df_cli = get_dataframe_with_cols(clientes_vis, ["nome","email","telefone","endereco","cadastro","status"])
            st.dataframe(df_cli)
            col1, col2 = st.columns(2)
            with col1:
                csv = df_cli.to_csv(index=False).encode("utf-8")
                st.download_button("Baixar CSV", data=csv, file_name="clientes.csv", mime="text/csv")
            with col2:
                texto = "\n".join(
                    f"{c['nome']} | {c['email']} | {c['telefone']} | {c['status']}" 
                    for c in clientes_vis
                )
                pdf_file = exportar_pdf(texto, nome_arquivo="clientes")
                with open(pdf_file, "rb") as f:
                    st.download_button("Baixar PDF", f, file_name=pdf_file)
        else:
            st.info("Nenhum cliente encontrado.")

    # ------------------ Gestão de Leads ------------------ #
    elif escolha == "Gestão de Leads":
        st.subheader("📇 Gestão de Leads")
        with st.form("form_lead"):
            nome = st.text_input("Nome*", key="nome_lead")
            contato = st.text_input("Contato*")
            email = st.text_input("E-mail*")
            data_aniv = st.date_input("Data de Aniversário")
            if st.form_submit_button("Salvar Lead"):
                if not (nome and contato and email):
                    st.warning("Preencha todos os campos!")
                else:
                    novo = {
                        "nome": nome, "contato": contato,
                        "email": email,
                        "data_aniversario": data_aniv.strftime("%Y-%m-%d")
                    }
                    if enviar_dados_para_planilha("Lead", novo):
                        LEADS = carregar_dados_da_planilha("Lead")
                        st.success("Lead salvo!")
        st.subheader("Lista de Leads")
        if LEADS:
            df_l = get_dataframe_with_cols(LEADS, ["nome","contato","email","data_aniversario"])
            st.dataframe(df_l)
            c1, c2 = st.columns(2)
            with c1:
                csv = df_l.to_csv(index=False).encode("utf-8")
                st.download_button("Baixar CSV", data=csv, file_name="leads.csv", mime="text/csv")
            with c2:
                txt = "\n".join(f"{l['nome']} | {l['contato']} | {l['email']}" for l in LEADS)
                pdf = exportar_pdf(txt, nome_arquivo="leads")
                with open(pdf, "rb") as f:
                    st.download_button("Baixar PDF", f, file_name=pdf)
        else:
            st.info("Nenhum lead cadastrado.")

    # ------------------ Processos ------------------ #
    elif escolha == "Processos":
        st.subheader("📄 Cadastro de Processos")
        with st.form("form_processo"):
            cliente = st.text_input("Cliente*")
            numero = st.text_input("Número do Processo*")
            contrato = st.selectbox("Tipo de Contrato*", ["Fixo","Por Ato","Contingência"])
            descricao = st.text_area("Descrição*")
            valor_tot = st.number_input("Valor Total (R$)*", min_value=0.0, format="%.2f")
            valor_mov = st.number_input("Valor Movimentado (R$)", min_value=0.0, format="%.2f")
            prazo_ini = st.date_input("Prazo Inicial*", value=datetime.date.today())
            prazo_fim = st.date_input("Prazo Final*", value=datetime.date.today()+datetime.timedelta(days=30))
            mov = st.checkbox("Houve movimentação?")
            area = st.selectbox("Área Jurídica*", ["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
            link = st.text_input("Link Material (opcional)")
            encerrado = st.checkbox("Processo Encerrado?")
            if st.form_submit_button("Salvar Processo"):
                if not (cliente and numero and descricao):
                    st.warning("Preencha os campos obrigatórios!")
                else:
                    novo = {
                        "cliente":cliente, "numero":numero,
                        "contrato":contrato,"descricao":descricao,
                        "valor_total":valor_tot,"valor_movimentado":valor_mov,
                        "prazo_inicial":prazo_ini.strftime("%Y-%m-%d"),
                        "prazo":prazo_fim.strftime("%Y-%m-%d"),
                        "houve_movimentacao":mov,"encerrado":encerrado,
                        "area":area,"responsavel":st.session_state.usuario,
                        "link_material":link,
                        "data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    if enviar_dados_para_planilha("Processo", novo):
                        PROCESSOS.append(novo)
                        st.success("Processo cadastrado!")

        st.subheader("📋 Lista de Processos")
        if PROCESSOS:
            df_p = get_dataframe_with_cols(PROCESSOS, ["numero","cliente","area","prazo","responsavel"])
            # Status calculado omitido para brevidade
            st.dataframe(df_p)
            c1, c2 = st.columns(2)
            with c1:
                csv = df_p.to_csv(index=False).encode("utf-8")
                st.download_button("Baixar CSV", data=csv, file_name="processos.csv", mime="text/csv")
            with c2:
                txt = "\n".join(f"{p['numero']} | {p['cliente']} | {p['area']}" for p in PROCESSOS)
                pdf = exportar_pdf(txt, nome_arquivo="processos")
                with open(pdf, "rb") as f:
                    st.download_button("Baixar PDF", f, file_name=pdf)
        else:
            st.info("Nenhum processo cadastrado.")

    # ------------------ Históricos ------------------ #
    elif escolha == "Históricos":
        st.subheader("📜 Histórico de Processos + Consulta TJMG")
        num = st.text_input("Número do Processo")
        if num:
            hist = [h for h in HISTORICO if h.get("numero")==num]
            if hist:
                for item in hist:
                    with st.expander(f"{item['tipo']} - {item['data']}"):
                        st.write(item.get("conteudo",""))
            else:
                st.info("Nenhum histórico encontrado.")
        iframe = """
        <iframe src="https://www.tjmg.jus.br/portal-tjmg/processos/andamento-processual/"
                style="width:100%; height:600px; border:none;" scrolling="yes"></iframe>
        """
        st.components.v1.html(iframe, height=600)
        
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
