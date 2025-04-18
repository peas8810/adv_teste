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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = os.getenv("GAS_WEB_APP_URL")

# -------------------- Usuários Persistidos --------------------
if "USERS" not in st.session_state:
    st.session_state.USERS = {
        "dono": {"username": "dono", "senha": "dono123", "papel": "owner"},
        "gestor1": {"username": "gestor1", "senha": "gestor123", "papel": "manager", "escritorio": "Escritório A", "area": "Todas"},
        "adv1":   {"username": "adv1",   "senha": "adv123",   "papel": "lawyer",  "escritorio": "Escritório A", "area": "Criminal"}
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

@st.cache_data(ttl=300)
def carregar_dados_da_planilha(tipo):
    try:
        resp = requests.get(GAS_WEB_APP_URL, params={"tipo": tipo}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Erro ao carregar {tipo}: {e}")
        return []

@st.cache_data(ttl=300)
def carregar_usuarios_da_planilha():
    funcs = carregar_dados_da_planilha("Funcionario") or []
    users = {}
    if not funcs:
        users.update(st.session_state.USERS)
        return users
    for f in funcs:
        key = f.get("usuario")
        if key:
            users[key] = {
                "username": key,
                "senha": f.get("senha", ""),
                "papel": f.get("papel", "assistant"),
                "escritorio": f.get("escritorio", "Global"),
                "area": f.get("area", "Todas")
            }
    return users

def login(usuario, senha):
    u = st.session_state.USERS.get(usuario)
    return u if u and u.get("senha") == senha else None


def calcular_status_processo(data_prazo, houve_movimentacao, encerrado=False):
    if encerrado:
        return "⚫ Encerrado"
    hoje = datetime.date.today()
    dias = (data_prazo - hoje).days
    if houve_movimentacao:
        return "🔵 Movimentado"
    if dias < 0:
        return "🔴 Atrasado"
    if dias <= 10:
        return "🟡 Atenção"
    return "🟢 Normal"

# Exportadores
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

# Interface Principal
 def main():
    st.title("Sistema Jurídico")

    # Atualiza usuários
    st.session_state.USERS = carregar_usuarios_da_planilha()

    # Carrega dados
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HISTORICOS = carregar_dados_da_planilha("Historico_Peticao") or []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []

    # Login
    with st.sidebar:
        st.header("🔐 Login")
        user_in = st.text_input("Usuário")
        pwd_in = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = login(user_in, pwd_in)
            if user:
                st.session_state.usuario = user_in
                st.session_state.papel = user.get("papel")
                st.session_state.dados_usuario = user
                st.success("Login efetuado!")
            else:
                st.error("Credenciais inválidas.")
        if "usuario" in st.session_state and st.button("Sair"):
            for k in ["usuario","papel","dados_usuario"]:
                st.session_state.pop(k, None)
            st.experimental_rerun()

    # Se logado
    if "usuario" in st.session_state:
        papel = st.session_state.papel
        esc_usuario = st.session_state.dados_usuario.get("escritorio","Global")
        area_usuario = st.session_state.dados_usuario.get("area","Todas")
        st.sidebar.success(f"{st.session_state.usuario} ({papel})")

        # Menu
        op = ["Dashboard","Clientes","Processos","Históricos","Gerenciar Funcionários"]
        if papel == "owner":
            op += ["Gerenciar Escritórios","Gerenciar Permissões"]
        escolha = st.sidebar.selectbox("Menu", op)

        # Dashboard
        if escolha == "Dashboard":
            st.subheader("📋 Painel de Controle de Processos")
            with st.expander("🔍 Filtros", expanded=True):
                c1,c2,c3 = st.columns(3)
                filtro_area = area_usuario if area_usuario!="Todas" else c1.selectbox("Área", ["Todas"]+[p["area"] for p in PROCESSOS])
                filtro_status = c2.selectbox("Status", ["Todos","🔴 Atrasado","🟡 Atenção","🟢 Normal","🔵 Movimentado","⚫ Encerrado"])
                filtro_esc = c3.selectbox("Escritório", ["Todos"]+[p["escritorio"] for p in PROCESSOS])
            procs = PROCESSOS.copy()
            # aplica filtros...
            # totalizações e métricas
            total = len(procs)
            atras = len([p for p in procs if calcular_status_processo(converter_data(p.get("prazo")),p.get("houve_movimentacao"),p.get("encerrado"))=="🔴 Atrasado"])
            atenc = len([p for p in procs if calcular_status_processo(converter_data(p.get("prazo")),p.get("houve_movimentacao"),p.get("encerrado"))=="🟡 Atenção"])
            mov = len([p for p in procs if p.get("houve_movimentacao")])
            encer = len([p for p in procs if p.get("encerrado")])
            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("Total", total)
            c2.metric("Atrasados", atras)
            c3.metric("Atenção", atenc)
            c4.metric("Movimentados", mov)
            c5.metric("Encerrados", encer)
            # aniversários de cadastro
            hoje = datetime.date.today()
            anivers = []
            for c in CLIENTES:
                cad = c.get("cadastro","")
                try:
                    d = datetime.datetime.fromisoformat(cad[:19]).date()
                    if d.month==hoje.month and d.day==hoje.day:
                        anivers.append(c.get("nome"))
                except:
                    pass
            st.markdown("### 🎉 Aniversário de Cadastro")
            if anivers:
                for nome in anivers:
                    st.write(nome)
            else:
                st.info("Nenhum aniversário de cadastro hoje.")

        # Clientes
        elif escolha == "Clientes":
            st.subheader("👥 Cadastro de Clientes")
            with st.form("form_cliente"):
                nome = st.text_input("Nome Completo*")
                email = st.text_input("E-mail*")
                tel = st.text_input("Telefone*")
                nasc = st.date_input("Data de Nascimento")
                end = st.text_input("Endereço*")
                esc = st.selectbox("Escritório", [e["nome"] for e in ESCRITORIOS]+["Outro"])
                tipo = st.selectbox("Tipo de Cliente", ["Ativo","Inativo","Lead"])
                obs = st.text_area("Observações")
                if st.form_submit_button("Salvar Cliente"):
                    novo = {"nome":nome,"email":email,"telefone":tel,"aniversario":nasc.isoformat(),"endereco":end,"tipo_cliente":tipo,"observacoes":obs,"cadastro":datetime.datetime.now().isoformat(),"responsavel":st.session_state.usuario,"escritorio":esc}
                    if enviar_dados_para_planilha("Cliente",novo):
                        st.success("Cliente salvo!")
            if CLIENTES:
                df = pd.DataFrame(CLIENTES)
                st.dataframe(df[["nome","email","telefone","tipo_cliente","cadastro"]])
                a1,a2 = st.columns(2)
                with a1:
                    txt = "\n".join([f"{c['nome']} | {c['tipo_cliente']}" for c in CLIENTES])
                    st.download_button("TXT Clientes",txt,file_name="clientes.txt")
                with a2:
                    pdf = exportar_pdf(txt,"clientes")
                    with open(pdf,"rb") as f:
                        st.download_button("PDF Clientes",f,file_name=pdf)

        # Processos
        elif escolha == "Processos":
            st.subheader("📄 Cadastro de Processos")
            with st.form("form_processo"):
                cli = st.selectbox("Cliente*",[c["nome"] for c in CLIENTES])
                num = st.text_input("Número do Processo*")
                contrato = st.selectbox("Tipo de Contrato",["Fixo","Por Ato","Contingência"])
                desc = st.text_area("Descrição*")
                col1,col2 = st.columns(2)
                val_tot = col1.number_input("Valor Total",0.0)
                val_mov = col2.number_input("Valor Movimentado",0.0)
                prazo_ini = st.date_input("Prazo Inicial",datetime.date.today())
                prazo_fim = st.date_input("Prazo Final",datetime.date.today()+datetime.timedelta(days=30))
                mov = st.checkbox("Houve Movimentação?")
                area = st.selectbox("Área Jurídica",["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
                link = st.text_input("Link Material (opcional)")
                encer = st.checkbox("Encerrado?")
                if st.form_submit_button("Salvar Processo"):
                    novo = {"cliente":cli,"numero":num,"contrato":contrato,"descricao":desc,"valor_total":val_tot,"valor_movimentado":val_mov,"prazo_inicial":prazo_ini.isoformat(),"prazo":prazo_fim.isoformat(),"houve_movimentacao":mov,"encerrado":encer,"escritorio":esc_usuario,"area":area,"responsavel":st.session_state.usuario,"link_material":link,"data_cadastro":datetime.datetime.now().isoformat()}
                    if enviar_dados_para_planilha("Processo",novo):
                        st.success("Processo salvo!")

        # Históricos
        elif escolha == "Históricos":
            st.subheader("📜 Histórico de Processos")
            sel = st.selectbox("Processo",[p["numero"] for p in PROCESSOS])
            regs = [h for h in HISTORICOS if h.get("numero")==sel]
            if regs:
                for h in regs:
                    with st.expander(f"{h['tipo']} - {h['data']}"):
                        st.write(h.get("conteudo",""))
            else:
                st.info("Sem histórico cadastrado.")
            # iframe TJMG
            html = '<iframe src="https://www.tjmg.jus.br/portal-tjmg/processos/andamento-processual/" width="100%" height="600px"></iframe>'
            st.components.v1.html(html, height=600)

        # Gerenciar Funcionários
        elif escolha == "Gerenciar Funcionários":
            st.subheader("👥 Funcionários")
            with st.form("form_func"): 
                nome = st.text_input("Nome Completo*")
                email = st.text_input("E-mail*")
                tel = st.text_input("Telefone*")
                usr = st.text_input("Usuário*")
                pwd = st.text_input("Senha*",type="password")
                esc = st.selectbox("Escritório",[e["nome"] for e in ESCRITORIOS])
                area = st.selectbox("Área",["Cível","Criminal","Trabalhista","Previdenciário","Tributário","Todas"])
                papel = st.selectbox("Papel",["manager","lawyer","assistant"])
                sit = st.selectbox("Situação",["Ativo","Inativo"])
                if st.form_submit_button("Salvar Funcionário"):
                    f = {"nome":nome,"email":email,"telefone":tel,"usuario":usr,"senha":pwd,"escritorio":esc,"area":area,"papel":papel,"situacao":sit,"data_cadastro":datetime.datetime.now().isoformat(),"cadastrado_por":st.session_state.usuario}
                    if enviar_dados_para_planilha("Funcionario",f):
                        st.success("Funcionário salvo!")
            if FUNCIONARIOS:
                df = pd.DataFrame(FUNCIONARIOS)
                st.dataframe(df[["nome","usuario","papel","escritorio","area","situacao"]])
                c1,c2 = st.columns(2)
                with c1:
                    txt = "\n".join([f"{f['nome']}|{f['situacao']}" for f in FUNCIONARIOS])
                    st.download_button("TXT Funcionários",txt,file_name="funcionarios.txt")
                with c2:
                    pdf = exportar_pdf(txt,"funcionarios")
                    with open(pdf,"rb") as fp:
                        st.download_button("PDF Funcionários",fp,file_name=pdf)

        # Gerenciar Escritórios
        elif escolha == "Gerenciar Escritórios" and papel=="owner":
            st.subheader("🏢 Escritórios")
            t1,t2,t3 = st.tabs(["Cadastrar","Lista","Administradores"])
            with t1:
                st.info("Formulário de cadastro de escritório...")
            with t2:
                if ESCRITORIOS:
                    df = pd.DataFrame(ESCRITORIOS)
                    st.dataframe(df[["nome","endereco","telefone","email","cnpj"]])
            with t3:
                sel = st.selectbox("Escritório",[e['nome'] for e in ESCRITORIOS])
                admins = [f for f in FUNCIONARIOS if f.get('escritorio')==sel and f.get('papel')=='manager']
                if admins:
                    st.dataframe(pd.DataFrame(admins)[['nome','usuario']])
                else:
                    st.info("Sem administradores cadastrados.")

        # Gerenciar Permissões
        elif escolha == "Gerenciar Permissões" and papel=="owner":
            st.subheader("🔧 Permissões")
            if FUNCIONARIOS:
                df = pd.DataFrame(FUNCIONARIOS)
                st.dataframe(df)
                esc_sel = st.selectbox("Funcionário",df['nome'].tolist())
                novas = st.multiselect("Áreas",["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
                if st.button("Atualizar"):    
                    for i,f in enumerate(FUNCIONARIOS):
                        if f['nome']==esc_sel:
                            FUNCIONARIOS[i]['area']=','.join(novas)
                            enviar_dados_para_planilha("Funcionario",{"nome":esc_sel,"area":FUNCIONARIOS[i]['area'],"atualizar":True})
                            st.success("Permissões atualizadas")
                c1,c2 = st.columns(2)
                with c1:
                    txt = "\n".join([f"{f['nome']}|{f['area']}" for f in FUNCIONARIOS])
                    st.download_button("TXT Permissões",txt,file_name="permissoes.txt")
                with c2:
                    pdf=exportar_pdf(txt,"permissoes")
                    with open(pdf,'rb') as fp:
                        st.download_button("PDF Permissões",fp,file_name=pdf)
    else:
        st.info("Faça login para acessar.")

if __name__=='__main__':
    main()
