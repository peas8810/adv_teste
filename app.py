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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-590cfea82f49426c94ff423d41a91f49")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# -------------------- Usuários Persistidos --------------------
if "USERS" not in st.session_state:
    st.session_state.USERS = {
        "dono": {"username": "dono", "senha": "dono123", "papel": "owner"},
        "gestor1": {"username": "gestor1", "senha": "gestor123", "papel": "manager", "escritorio": "Escritorio A", "area": "Todas"},
        "adv1": {"username": "adv1", "senha": "adv123", "papel": "lawyer", "escritorio": "Escritorio A", "area": "Criminal"}
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
        st.error(f"Erro no envio: {response.text}")
        return False
    except Exception as e:
        st.error(f"Erro ao enviar dados ({tipo}): {e}")
        return False

@st.cache_data(ttl=300)
def carregar_usuarios_da_planilha():
    funcionarios = carregar_dados_da_planilha("Funcionario") or []
    if not funcionarios:
        return {"dono": {"username": "dono", "senha": "dono123", "papel": "owner", "escritorio": "Global", "area": "Todas"}}
    users = {}
    for f in funcionarios:
        key = f.get("usuario")
        if not key: continue
        users[key] = {
            "username": key,
            "senha": f.get("senha", ""),
            "papel": f.get("papel", "assistant"),
            "escritorio": f.get("escritorio", "Global"),
            "area": f.get("area", "Todas")
        }
    return users

def login(usuario, senha):
    user = st.session_state.USERS.get(usuario)
    return user if user and user.get("senha") == senha else None

def calcular_status_processo(data_prazo, houve_movimentacao, encerrado=False):
    if encerrado: return "⚫ Encerrado"
    dias = (data_prazo - datetime.date.today()).days
    if houve_movimentacao: return "🔵 Movimentado"
    if dias < 0: return "🔴 Atrasado"
    if dias <= 10: return "🟡 Atenção"
    return "🟢 Normal"

def exportar_pdf(texto, nome_arquivo="relatorio"):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, texto); pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def exportar_docx(texto, nome_arquivo="relatorio"):
    doc = Document(); doc.add_paragraph(texto); doc.save(f"{nome_arquivo}.docx")
    return f"{nome_arquivo}.docx"

def gerar_relatorio_pdf(dados, nome_arquivo="relatorio"):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Relatório de Processos", ln=1, align='C'); pdf.ln(10)
    headers = ["Cliente","Número","Área","Status","Responsável"]; widths=[40,30,50,30,40]
    for h,w in zip(headers,widths): pdf.cell(w,10,txt=h,border=1)
    pdf.ln()
    for p in dados:
        status = calcular_status_processo(converter_data(p.get("prazo")), p.get("houve_movimentacao",False), p.get("encerrado",False))
        row=[p.get("cliente",""),p.get("numero",""),p.get("area",""),status,p.get("responsavel","")]
        for v,w in zip(row,widths): pdf.cell(w,10,txt=str(v),border=1)
        pdf.ln()
    pdf.output(f"{nome_arquivo}.pdf"); return f"{nome_arquivo}.pdf"

@st.cache_data(ttl=300)
def aplicar_filtros(dados, filtros):
    def extrar(r):
        ds=r.get("data_cadastro") or r.get("cadastro"); return None if not ds else datetime.date.fromisoformat(ds[:10])
    res=[]
    for r in dados:
        ok=True; dr=extrar(r)
        for c,v in filtros.items():
            if not v: continue
            if c=="data_inicio" and (dr is None or dr<v): ok=False; break
            if c=="data_fim" and (dr is None or dr>v): ok=False; break
            if c not in ["data_inicio","data_fim"] and v.lower() not in str(r.get(c,"")).lower(): ok=False; break
        if ok: res.append(r)
    return res

def get_dataframe_with_cols(data, cols):
    df=pd.DataFrame(data if isinstance(data,list) else [data])
    for c in cols: df[c] = df.get(c, "")
    return df[cols]

##############################
# Interface Principal
##############################
def main():
    st.title("Sistema Jurídico")
    st.session_state.USERS = carregar_usuarios_da_planilha()
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HISTORICO = carregar_dados_da_planilha("Historico_Peticao") or []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []
    LEADS = carregar_dados_da_planilha("Lead") or []

    with st.sidebar:
        st.header("🔐 Login")
        u=st.text_input("Usuário"); s=st.text_input("Senha",type="password")
        if st.button("Entrar"):
            usr=login(u,s)
            if usr:
                st.session_state.usuario=u; st.session_state.papel=usr.get("papel"); st.session_state.dados_usuario=usr
                st.success("Login realizado com sucesso!")
            else: st.error("Credenciais inválidas")
        if st.session_state.get("usuario") and st.button("Sair"):
            for k in ["usuario","papel","dados_usuario"]: st.session_state.pop(k,None)
            st.sidebar.success("Você saiu do sistema!"); st.experimental_rerun()

    if not st.session_state.get("usuario"):
        return st.info("Por favor, faça login para acessar o sistema.")

    papel=st.session_state.papel; esc=st.session_state.dados_usuario.get("escritorio","Global"); area=st.session_state.dados_usuario.get("area","Todas")
    st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")

    menu=["Dashboard","Clientes","Gestão de Leads","Processos","Históricos"]
    if papel in ["owner","manager"]: menu.append("Relatórios")
    if papel in ["manager"]: menu.append("Gerenciar Funcionários")
    if papel=="owner": menu+= ["Gerenciar Escritórios","Gerenciar Permissões"]
    escolha=st.sidebar.selectbox("Menu",menu)

    # Dashboard
    if escolha=="Dashboard":
        # ... mantém lógica existente do dashboard com métricas ...
        pass

    # Clientes
    elif escolha=="Clientes":
        st.subheader("👥 Cadastro de Clientes")
        with st.form("form_cli"):
            nome=st.text_input("Nome Completo*",key="cli_nome"); email=st.text_input("E-mail*"); tel=st.text_input("Telefone*")
            aniv=st.date_input("Data de Nascimento"); end=st.text_input("Endereço*",placeholder="Rua, número,...")
            esc_sel=st.selectbox("Escritório",[e["nome"] for e in ESCRITORIOS]+["Outro"]); obs=st.text_area("Observações")
            if st.form_submit_button("Salvar Cliente"):
                if not all([nome,email,tel,end]): st.warning("Campos obrigatórios não preenchidos!")
                else:
                    c={"nome":nome,"email":email,"telefone":tel,"aniversario":aniv.strftime("%Y-%m-%d"),
                       "endereco":end,"observacoes":obs,
                       "cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "responsavel":st.session_state.usuario,"escritorio":esc_sel}
                    if enviar_dados_para_planilha("Cliente",c): CLIENTES.append(c); st.success("Cliente cadastrado com sucesso!")
        st.subheader("Lista de Clientes")
        if CLIENTES:
            df=get_dataframe_with_cols(CLIENTES,["nome","email","telefone","endereco","cadastro"]); st.dataframe(df)
            c1,c2=st.columns(2)
            with c1:
                if st.button("Exportar Clientes (TXT)"): txt="\n".join([f"{x['nome']}|{x['email']}|{x['telefone']}" for x in CLIENTES]); st.download_button("Baixar TXT",txt,file_name="clientes.txt")
            with c2:
                if st.button("Exportar Clientes (PDF)"): txt="\n".join([f"{x['nome']}|{x['email']}|{x['telefone']}" for x in CLIENTES]); f=exportar_pdf(txt,"clientes"); 
                    with open(f,"rb") as fb: st.download_button("Baixar PDF",fb,file_name=f)
        else: st.info("Nenhum cliente cadastrado ainda.")

    # Gestão de Leads
    elif escolha=="Gestão de Leads":
        st.subheader("📇 Gestão de Leads")
        with st.form("form_lead"):
            n=st.text_input("Nome*",key="lead_nome"); ct=st.text_input("Contato*"); em=st.text_input("E-mail*")
            da=st.date_input("Data de Aniversário")
            if st.form_submit_button("Salvar Lead"):
                if not all([n,ct,em]): st.warning("Preencha todos os campos obrigatórios!")
                else:
                    l={"nome":n,"numero":ct,"tipo_email":em,"data_aniversario":da.strftime("%Y-%m-%d"),
                       "origem":"lead","data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                    if enviar_dados_para_planilha("Lead",l): LEADS=carregar_dados_da_planilha("Lead"); st.success("Lead cadastrado com sucesso!")
        st.subheader("Lista de Leads")
        if LEADS:
            df=get_dataframe_with_cols(LEADS,["nome","numero","tipo_email","data_aniversario","origem","data_cadastro"]); st.dataframe(df)
            l1,l2=st.columns(2)
            with l1:
                if st.button("Exportar Leads (TXT)"): txt="\n".join([f"{x['nome']}|{x['numero']}|{x['tipo_email']}" for x in LEADS]); st.download_button("Baixar TXT",txt,file_name="leads.txt")
            with l2:
                if st.button("Exportar Leads (PDF)"): txt="\n".join([f"{x['nome']}|{x['numero']}|{x['tipo_email']}" for x in LEADS]); f=exportar_pdf(txt,"leads"); 
                    with open(f,"rb") as fb: st.download_button("Baixar PDF",fb,file_name=f)
        else: st.info("Nenhum lead cadastrado ainda.")

    # Processos
    elif escolha=="Processos":
        st.subheader("📄 Cadastro de Processos")
        with st.form("form_proc"):
            cli=st.text_input("Cliente*"); num=st.text_input("Número do Processo*")
            tc=st.selectbox("Tipo de Contrato*",["Fixo","Por Ato","Contingência"]);
            desc=st.text_area("Descrição do Caso*")
            c1,c2=st.columns(2)
            with c1: vt=st.number_input("Valor Total (R$)*",min_value=0.0,format="%.2f")
            with c2: vm=st.number_input("Valor Movimentado (R$)",min_value=0.0,format="%.2f")
            pin=st.date_input("Prazo Inicial*",value=datetime.date.today()); pfin=st.date_input("Prazo Final*",value=datetime.date.today()+datetime.timedelta(days=30))
            mov=st.checkbox("Houve movimentação recente?"); area_sel=st.selectbox("Área Jurídica*",["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
            if area!='Todas': area_sel=area
            link=st.text_input("Link Material (opcional)"); enc=st.checkbox("Processo Encerrado?")
            if st.form_submit_button("Salvar Processo"):
                if not all([cli,num,desc]): st.warning("Campos obrigatórios não preenchidos!")
                else:
                    p={"cliente":cli,"numero":num,"contrato":tc,"descricao":desc,"valor_total":vt,
                       "valor_movimentado":vm,"prazo_inicial":pin.strftime("%Y-%m-%d"),"prazo":pfin.strftime("%Y-%m-%d"),
                       "houve_movimentacao":mov,"encerrado":enc,"escritorio":esc,"area":area_sel,
                       "responsavel":st.session_state.usuario,"link_material":link,
                       "data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                    if enviar_dados_para_planilha("Processo",p): PROCESSOS.append(p); st.success("Processo cadastrado com sucesso!")
        st.subheader("Lista de Processos")
        if PROCESSOS:
            df=get_dataframe_with_cols(PROCESSOS,["numero","cliente","area","prazo","responsavel","link_material"] )
            df['Status']=df.apply(lambda r: calcular_status_processo(converter_data(r['prazo']),r.get('houve_movimentacao',False),r.get('encerrado',False)), axis=1)
            df=df.sort_values(by='Status', key=lambda x: x.map({"🔴 Atrasado":0,"🟡 Atenção":1,"🟢 Normal":2,"🔵 Movimentado":3,"⚫ Encerrado":4}))
            st.dataframe(df)
            p1,p2=st.columns(2)
            with p1:
                if st.button("Exportar Processos (TXT)"): txt="\n".join([f"{x['numero']}|{x['cliente']}|{x['area']}" for x in PROCESSOS]); st.download_button("Baixar TXT",txt,file_name="processos.txt")
            with p2:
                if st.button("Exportar Processos (PDF)"): txt="\n".join([f"{x['numero']}|{x['cliente']}|{x['area']}" for x in PROCESSOS]); f=exportar_pdf(txt,"processos"); with open(f,"rb") as fb: st.download_button("Baixar PDF",fb,file_name=f)
        else: st.info("Nenhum processo cadastrado ainda.")

    # Históricos + TJMG
    elif escolha=="Históricos":
        st.subheader("📜 Histórico de Processos + Consulta TJMG")
        np=st.text_input("Digite número do processo")
        if np:
            hf=[h for h in HISTORICO if h.get('numero')==np]
            if hf:
                for h in hf:
                    with st.expander(f"{h['tipo']} - {h['data']}"): st.write(h['conteudo'])
            else: st.info("Nenhum histórico encontrado.")
        iframe="""<div style=\"overflow:auto;height:600px;\"><iframe src=\"https://www.tjmg.jus.br/portal-tjmg/processos/andamento-processual/\" style=\"width:100%;height:100%;border:none;\" scrolling=\"yes\"></iframe></div>"""
        st.components.v1.html(iframe,height=600)

    # Relatórios
    elif escolha=="Relatórios":
        st.subheader("📊 Relatórios Personalizados")
        with st.expander("🔍 Filtros",expanded=True):
            tr=st.selectbox("Tipo de Relatório",["Processos","Escritórios","Clientes","Leads","Funcionários"])
            di=st.date_input("Data Início"); df=st.date_input("Data Fim")
            fmt=st.selectbox("Formato",["PDF","DOCX","CSV"])
            if st.button("Aplicar Filtros"): 
                filt={"data_inicio":di,"data_fim":df}
                dados=
                    PROCESSOS if tr=="Processos" else ESCRITORIOS if tr=="Escritórios" else CLIENTES if tr=="Clientes" else LEADS if tr=="Leads" else FUNCIONARIOS
                res=aplicar_filtros(dados,filt); st.session_state.dados_relatorio=res; st.session_state.tipo_rel=tr
        dr=st.session_state.get('dados_relatorio',[])
        if dr:
            st.write(f"{st.session_state.tipo_rel} encontrados: {len(dr)}")
            if st.button(f"Exportar ({fmt})"):
                if fmt=="PDF": arq=gerar_relatorio_pdf(dr) if st.session_state.tipo_rel=="Processos" else exportar_pdf(str(dr));
                elif fmt=="DOCX": arq=exportar_docx("\n".join(map(str,dr)))
                else:
                    dfc=pd.DataFrame(dr); csv= dfc.to_csv(index=False).encode('utf-8'); st.download_button("Baixar CSV",data=csv,file_name=f"relatorio_{datetime.datetime.now():%Y%m%d}.csv",mime="text/csv"); st.dataframe(dfc); return
                with open(arq,'rb') as fa: st.download_button("Baixar Arquivo",fa,file_name=arq)

    # Gerenciar Funcionários
    elif escolha=="Gerenciar Funcionários":
        st.subheader("👥 Cadastro de Funcionários")
        with st.form("form_func"):
            n=st.text_input("Nome*"); e=st.text_input("E-mail*"); t=st.text_input("Telefone*")
            u=st.text_input("Usuário*"); s=st.text_input("Senha*",type="password")
            es=st.selectbox("Escritório*",[e['nome'] for e in ESCRITORIOS] or ["Global"])
            a=st.selectbox("Área*",["Cível","Criminal","Trabalhista","Previdenciário","Tributário","Todas"])
            p=st.selectbox("Papel",["manager","lawyer","assistant"])
            if st.form_submit_button("Cadastrar"): 
                if not all([n,e,t,u,s]): st.warning("Campos obrigatórios!")
                else:
                    f={"nome":n,"email":e,"telefone":t,"usuario":u,"senha":s,"escritorio":es,"area":a,"papel":p,
                       "data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"cadastrado_por":st.session_state.usuario}
                    if enviar_dados_para_planilha("Funcionario",f): st.success("Funcionario cadastrado!"); st.session_state.USERS=carregar_usuarios_da_planilha()
        st.subheader("Lista de Funcionários")
        vis=FUNCIONARIOS if papel!="manager" else [x for x in FUNCIONARIOS if x.get('escritorio')==esc]
        if vis:
            df=get_dataframe_with_cols(vis,["nome","email","telefone","usuario","papel","escritorio","area"]); st.dataframe(df)
            c1,c2=st.columns(2)
            with c1:
                if st.button("Exportar Funcionários (TXT)"): txt="\n".join([f"{x['nome']}|{x['email']}|{x['telefone']}" for x in vis]); st.download_button("Baixar TXT",txt,file_name="func.txt")
            with c2:
                if st.button("Exportar Funcionários (PDF)"): txt="\n".join([f"{x['nome']}|{x['email']}|{x['telefone']}" for x in vis]); f=exportar_pdf(txt,"func"); with open(f,'rb') as fb: st.download_button("Baixar PDF",fb,file_name=f)
        else: st.info("Nenhum funcionário cadastrado.")

    # Gerenciar Escritórios
    elif escolha=="Gerenciar Escritórios" and papel=="owner":
        st.subheader("🏢 Gerenciar Escritórios")
        tab1,tab2,tab3=st.tabs(["Cadastrar","Lista","Administradores"])
        with tab1:
            with st.form("form_esc"): 
                nome=st.text_input("Nome*",key="esc_nome"); end=st.text_input("Endereço*"); tel=st.text_input("Telefone*")
                em=st.text_input("E-mail*"); cnpj=st.text_input("CNPJ*")
                rt=st.text_input("Responsável Técnico*"); tel_t=st.text_input("Telefone Técnico*"); em_t=st.text_input("E-mail Técnico*")
                areas=st.multiselect("Áreas",["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
                if st.form_submit_button("Salvar Escritório"):
                    campos=[nome,end,tel,em,cnpj,rt,tel_t,em_t]
                    if not all(campos): st.warning("Preencha todos os campos!")
                    else:
                        escd={"nome":nome,"endereco":end,"telefone":tel,"email":em,"cnpj":cnpj,
                              "data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                              "responsavel":st.session_state.usuario,
                              "responsavel_tecnico":rt,"telefone_tecnico":tel_t,"email_tecnico":em_t,
                              "area_atuacao":", ".join(areas)}
                        if enviar_dados_para_planilha("Escritorio",escd): ESCRITORIOS.append(escd); st.success("Escritório cadastrado!")
        with tab2:
            if ESCRITORIOS:
                df=get_dataframe_with_cols(ESCRITORIOS,["nome","endereco","telefone","email","cnpj"]); st.dataframe(df)
                c1,c2=st.columns(2)
                with c1:
                    if st.button("Exportar Escritórios (TXT)"): txt="\n".join([f"{x['nome']}|{x['endereco']}|{x['telefone']}" for x in ESCRITORIOS]); st.download_button("Baixar TXT",txt,file_name="escr.txt")
                with c2:
                    if st.button("Exportar Escritórios (PDF)"): txt="\n".join([f"{x['nome']}|{x['endereco']}|{x['telefone']}" for x in ESCRITORIOS]); f=exportar_pdf(txt,"esc"); with open(f,'rb') as fb: st.download_button("Baixar PDF",fb,file_name=f)
            else: st.info("Nenhum escritório cadastrado.")
        with tab3:
            st.info("Funcionalidade de administradores em desenvolvimento.")

    # Gerenciar Permissões
    elif escolha=="Gerenciar Permissões" and papel=="owner":
        st.subheader("🔧 Gerenciar Permissões")
        if FUNCIONARIOS:
            df=pd.DataFrame(FUNCIONARIOS); st.dataframe(df)
            sel=st.selectbox("Funcionário",df['nome'].tolist()); nas=st.multiselect("Áreas",["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
            if st.button("Atualizar Permissões"):
                for f in FUNCIONARIOS:
                    if f.get('nome')==sel: f['area']=', '.join(nas)
                if enviar_dados_para_planilha("Funcionario",{"nome":sel,"area":', '.join(nas),"atualizar":True}): st.success("Permissões atualizadas!")
                else: st.error("Falha ao atualizar permissões.")
        else: st.info("Nenhum funcionário cadastrado.")

if __name__=="__main__":
    main()
