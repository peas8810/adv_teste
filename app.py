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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-…")
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
GAS_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzx0HbjObfhgU4lqVFBI05neopT-rb5tqlGbJU19EguKq8LmmtzkTPtZjnMgCNmz8OtLw/exec"

# -------------------- Usuários Persistidos --------------------
if "USERS" not in st.session_state:
    st.session_state.USERS = {
        "dono":    {"username":"dono","senha":"dono123","papel":"owner"},
        "gestor1": {"username":"gestor1","senha":"gestor123","papel":"manager","escritorio":"Escritorio A","area":"Todas"},
        "adv1":    {"username":"adv1","senha":"adv123","papel":"lawyer","escritorio":"Escritorio A","area":"Criminal"}
    }

# -------------------- Funções Auxiliares --------------------
def converter_data(data_str):
    if not data_str:
        return datetime.date.today()
    try:
        s = data_str.replace("Z","")
        if "T" in s:
            return datetime.datetime.fromisoformat(s).date()
        return datetime.date.fromisoformat(s)
    except:
        return datetime.date.today()

@st.cache_data(ttl=300, show_spinner=False)
def carregar_dados_da_planilha(tipo, debug=False):
    try:
        r = requests.get(GAS_WEB_APP_URL, params={"tipo":tipo}, timeout=10)
        r.raise_for_status()
        if debug:
            st.text(f"URL: {r.url}")
            st.text(f"Resp: {r.text[:200]}")
        return r.json()
    except Exception as e:
        st.error(f"Erro ao carregar {tipo}: {e}")
        return []

def enviar_dados_para_planilha(tipo, dados):
    try:
        payload = {"tipo":tipo, **dados}
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            r = client.post(GAS_WEB_APP_URL, json=payload)
        if r.text.strip()=="OK":
            return True
        st.error(f"Erro no envio: {r.text}")
        return False
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
        k = f.get("usuario")
        if not k: continue
        users[k] = {
            "username": k,
            "senha":    f.get("senha",""),
            "papel":    f.get("papel","assistant"),
            "escritorio": f.get("escritorio","Global"),
            "area":     f.get("area","Todas")
        }
    return users

def login(usuario, senha):
    u = st.session_state.USERS.get(usuario)
    if u and u["senha"]==senha:
        return u
    return None

def calcular_status_processo(prazo, moviment, encerrado=False):
    if encerrado: return "⚫ Encerrado"
    hoje = datetime.date.today()
    d = (prazo - hoje).days
    if moviment:          return "🔵 Movimentado"
    if d < 0:             return "🔴 Atrasado"
    if d <= 10:           return "🟡 Atenção"
    return "🟢 Normal"

def exportar_pdf(texto, nome_arquivo="relatorio"):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=12)
    pdf.multi_cell(0,10,texto); pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"

def exportar_docx(texto, nome_arquivo="relatorio"):
    doc = Document(); doc.add_paragraph(texto)
    doc.save(f"{nome_arquivo}.docx"); return f"{nome_arquivo}.docx"

def gerar_relatorio_pdf(dados, nome_arquivo="relatorio"):
    pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial",12)
    pdf.cell(200,10,"Relatório de Processos",ln=1,align='C'); pdf.ln(10)
    widths = [40,30,50,30,40]
    headers = ["Cliente","Número","Área","Status","Responsável"]
    for i,h in enumerate(headers): pdf.cell(widths[i],10,h,border=1)
    pdf.ln()
    for p in dados:
        prazo = converter_data(p.get("prazo")); status = calcular_status_processo(prazo,p.get("houve_movimentacao",False),p.get("encerrado",False))
        cols = [p.get("cliente",""),p.get("numero",""),p.get("area",""),status,p.get("responsavel","")]
        for i,c in enumerate(cols): pdf.cell(widths[i],10,str(c),border=1)
        pdf.ln()
    pdf.output(f"{nome_arquivo}.pdf"); return f"{nome_arquivo}.pdf"

def aplicar_filtros(dados, filtros):
    def extrair(r):
        s = r.get("data_cadastro") or r.get("cadastro") or ""
        try: return datetime.date.fromisoformat(s[:10])
        except: return None
    res = []
    for r in dados:
        ok = True; dt = extrair(r)
        for campo,val in filtros.items():
            if not val: continue
            if campo=="data_inicio" and (not dt or dt<val): ok=False; break
            if campo=="data_fim"    and (not dt or dt>val): ok=False; break
            if campo not in ["data_inicio","data_fim"] and val.lower() not in str(r.get(campo,"")).lower():
                ok=False; break
        if ok: res.append(r)
    return res

def atualizar_processo(numero, att):
    att["numero"]=numero; att["atualizar"]=True
    return enviar_dados_para_planilha("Processo",att)

def excluir_processo(numero):
    return enviar_dados_para_planilha("Processo",{"numero":numero,"excluir":True})

def get_dataframe_with_cols(data, cols):
    if isinstance(data,dict): data=[data]
    df = pd.DataFrame(data)
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df[cols]

# -------------------- Interface Principal --------------------
def main():
    st.title("Sistema Jurídico")
    # recarrega
    st.session_state.USERS = carregar_usuarios_da_planilha()
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HISTORICO_PETICOES = carregar_dados_da_planilha("Historico_Peticao") or []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []
    LEADS = carregar_dados_da_planilha("Lead") or []

    # Sidebar: login/logout
    with st.sidebar:
        st.header("🔐 Login")
        usr = st.text_input("Usuário")
        pwd = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            u = login(usr,pwd)
            if u:
                st.session_state.usuario = usr
                st.session_state.papel   = u["papel"]
                st.sidebar.success("Login realizado!")
                st.experimental_rerun()
            else:
                st.error("Credenciais inválidas")
        if "usuario" in st.session_state and st.button("Sair"):
            for k in ["usuario","papel"]: st.session_state.pop(k,None)
            st.sidebar.success("Desconectado")
            st.experimental_rerun()

    if "usuario" not in st.session_state:
        st.info("Faça login para acessar o sistema.")
        return

    papel = st.session_state.papel
    dados_u = st.session_state.USERS[st.session_state.usuario]
    esc_u = dados_u.get("escritorio","Global")
    area_u = dados_u.get("area","Todas")
    st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")

    # Menu
    opcs = ["Dashboard","Clientes","Gestão de Leads","Processos","Históricos","Relatórios","Gerenciar Funcionários"]
    if papel=="owner":
        opcs += ["Gerenciar Escritórios","Gerenciar Permissões"]
    escolha = st.sidebar.selectbox("Menu", opcs)

    # ------------------ Dashboard ------------------
    if escolha=="Dashboard":
        st.subheader("📋 Painel de Controle de Processos")
        # filtros
        with st.expander("🔍 Filtros",expanded=True):
            col1,col2,col3 = st.columns(3)
            if area_u!="Todas":
                filtro_area = area_u; st.info(f"Área fixa: {area_u}")
            else:
                filtro_area = col1.selectbox("Área",["Todas"]+list({p["area"] for p in PROCESSOS}))
            filtro_status    = col2.selectbox("Status",["Todos","🔴 Atrasado","🟡 Atenção","🟢 Normal","🔵 Movimentado","⚫ Encerrado"])
            filtro_escritorio= col3.selectbox("Escritório",["Todos"]+list({p["escritorio"] for p in PROCESSOS}))

        vis = PROCESSOS.copy()
        if area_u!="Todas":
            vis = [p for p in vis if p.get("area")==area_u]
        elif filtro_area!="Todas":
            vis = [p for p in vis if p.get("area")==filtro_area]
        if filtro_escritorio!="Todos":
            vis = [p for p in vis if p.get("escritorio")==filtro_escritorio]
        if filtro_status!="Todos":
            if filtro_status=="⚫ Encerrado":
                vis = [p for p in vis if p.get("encerrado",False)]
            else:
                vis = [p for p in vis if calcular_status_processo(converter_data(p.get("prazo")),p.get("houve_movimentacao",False),p.get("encerrado",False))==filtro_status]

        # métricas
        total      = len(vis)
        atrasados  = len([p for p in vis if calcular_status_processo(converter_data(p.get("prazo")),p.get("houve_movimentacao",False),p.get("encerrado",False))=="🔴 Atrasado"])
        atencao    = len([p for p in vis if calcular_status_processo(converter_data(p.get("prazo")),p.get("houve_movimentacao",False),p.get("encerrado",False))=="🟡 Atenção"])
        moviment   = len([p for p in vis if p.get("houve_movimentacao",False)])
        encerrados = len([p for p in vis if p.get("encerrado",False)])
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Total",total); c2.metric("Atrasados",atrasados)
        c3.metric("Atenção",atencao); c4.metric("Movimentados",moviment)
        c5.metric("Encerrados",encerrados)

        # aniversariantes
        hoje = datetime.date.today()
        anivs=[]
        for c in CLIENTES:
            try:
                d = datetime.date.fromisoformat(c.get("aniversario","")[:10])
                if d.month==hoje.month and d.day==hoje.day: anivs.append(c["nome"])
            except: pass
        st.markdown("### 🎂 Aniversariantes")
        if anivs: 
            for n in anivs: st.write(f"- {n}")
        else:
            st.info("Nenhum hoje.")

        # gráfico pizza
        if total>0:
            fig = px.pie(
                values=[atrasados,atencao,moviment,encerrados,total-(atrasados+atencao+moviment+encerrados)],
                names=["Atrasados","Atenção","Movimentados","Encerrados","Outros"],
                title="Distribuição",
                color_discrete_map={"Atrasados":"red","Atenção":"yellow","Movimentados":"blue","Encerrados":"black","Outros":"gray"}
            )
            st.plotly_chart(fig)

        # lista e edição
        st.subheader("📋 Lista de Processos")
        if vis:
            df = get_dataframe_with_cols(vis,["numero","cliente","area","prazo","responsavel","link_material"])
            df["Status"] = df.apply(lambda r: calcular_status_processo(converter_data(r["prazo"]),r.get("houve_movimentacao",False),r.get("encerrado",False)),axis=1)
            order={"🔴 Atrasado":0,"🟡 Atenção":1,"🟢 Normal":2,"🔵 Movimentado":3,"⚫ Encerrado":4}
            df["ord"] = df["Status"].map(order)
            df = df.sort_values("ord").drop("ord",axis=1)
            df["link_material"] = df["link_material"].apply(lambda x:f"[Abrir]({x})" if x else "")
            st.dataframe(df)
        else:
            st.info("Nenhum processo.")

        st.subheader("✏️ Editar/Excluir Processo")
        num = st.text_input("Número do processo para editar/excluir")
        if num:
            alvo = next((p for p in PROCESSOS if p.get("numero")==num),None)
            if alvo:
                with st.expander("Editar"):
                    cli = st.text_input("Cliente",alvo.get("cliente",""))
                    desc= st.text_area("Descrição",alvo.get("descricao",""))
                    opts=["🔴 Atrasado","🟡 Atenção","🟢 Normal","🔵 Movimentado","⚫ Encerrado"]
                    cur = calcular_status_processo(converter_data(alvo.get("prazo")),alvo.get("houve_movimentacao",False),alvo.get("encerrado",False))
                    idx = opts.index(cur) if cur in opts else 2
                    novo = st.selectbox("Status",opts,index=idx)
                    link = st.text_input("Link",alvo.get("link_material",""))
                    col_up,col_del=st.columns(2)
                    with col_up:
                        if st.button("Atualizar"):
                            att={"cliente":cli,"descricao":desc,"status_manual":novo,"link_material":link}
                            if atualizar_processo(num,att): st.success("Atualizado!") 
                            else: st.error("Falha ao atualizar.")
                    with col_del:
                        if papel in ["manager","owner"] and st.button("Excluir"):
                            if excluir_processo(num):
                                st.success("Excluído!"); PROCESSOS[:] = [p for p in PROCESSOS if p.get("numero")!=num]
                            else:
                                st.error("Falha ao excluir.")
            else:
                st.warning("Processo não encontrado.")

    # ------------------ Clientes ------------------
    elif escolha=="Clientes":
        st.subheader("👥 Cadastro de Clientes")
        with st.form("form_cliente"):
            nome      = st.text_input("Nome*",key="nome_cliente")
            email     = st.text_input("E-mail*")
            telefone  = st.text_input("Telefone*")
            aniversario = st.date_input("Nascimento")
            endereco  = st.text_input("Endereço*")
            escritorio = st.selectbox("Escritório",[e["nome"] for e in ESCRITORIOS]+["Outro"])
            observ    = st.text_area("Observações")
            if st.form_submit_button("Salvar Cliente"):
                if not all([nome,email,telefone,endereco]):
                    st.warning("Campos obrigatórios!")
                else:
                    novo = {
                        "nome":nome,"email":email,"telefone":telefone,
                        "aniversario":aniversario.strftime("%Y-%m-%d"),
                        "endereco":endereco,"observacoes":observ,
                        "cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "responsavel":st.session_state.usuario,
                        "escritorio":escritorio
                    }
                    if enviar_dados_para_planilha("Cliente",novo):
                        CLIENTES.append(novo); st.success("Cliente salvo!")

        st.subheader("Lista de Clientes")
        if CLIENTES:
            df = get_dataframe_with_cols(CLIENTES,["nome","email","telefone","endereco","cadastro"])
            st.dataframe(df)
            c1,c2 = st.columns(2)
            with c1:
                if st.button("Exportar TXT"):
                    txt = "\n".join(f"{c['nome']} | {c['email']} | {c['telefone']}" for c in CLIENTES)
                    st.download_button("Baixar TXT",txt,file_name="clientes.txt")
            with c2:
                if st.button("Exportar PDF"):
                    txt = "\n".join(f"{c['nome']} | {c['email']} | {c['telefone']}" for c in CLIENTES)
                    pdf = exportar_pdf(txt,"clientes")
                    with open(pdf,"rb") as f: st.download_button("Baixar PDF",f,file_name=pdf)
        else:
            st.info("Nenhum cliente.")

    # ------------------ Gestão de Leads ------------------
    elif escolha=="Gestão de Leads":
        st.subheader("📇 Gestão de Leads")
        with st.form("form_lead"):
            nome_lead = st.text_input("Nome*",key="nome_lead")
            contato   = st.text_input("Contato*")
            email_ld  = st.text_input("E-mail*")
            nasc_ld   = st.date_input("Nascimento")
            if st.form_submit_button("Salvar Lead"):
                if not all([nome_lead,contato,email_ld]):
                    st.warning("Preencha todos os campos!")
                else:
                    nl = {
                        "nome":nome_lead,"numero":contato,"email":email_ld,
                        "data_aniversario":nasc_ld.strftime("%Y-%m-%d"),
                        "origem":"lead",
                        "data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    if enviar_dados_para_planilha("Lead",nl):
                        LEADS[:] = carregar_dados_da_planilha("Lead") or []
                        st.success("Lead salvo!")

        st.subheader("Lista de Leads")
        if LEADS:
            df = get_dataframe_with_cols(LEADS,["nome","numero","email","data_aniversario","origem","data_cadastro"])
            st.dataframe(df)
            c1,c2 = st.columns(2)
            with c1:
                if st.button("Exportar TXT"):
                    txt="\n".join(f"{l['nome']} | {l['numero']} | {l['email']}" for l in LEADS)
                    st.download_button("Baixar TXT",txt,file_name="leads.txt")
            with c2:
                if st.button("Exportar PDF"):
                    txt="\n".join(f"{l['nome']} | {l['numero']} | {l['email']}" for l in LEADS)
                    pdf=exportar_pdf(txt,"leads")
                    with open(pdf,"rb") as f: st.download_button("Baixar PDF",f,file_name=pdf)
        else:
            st.info("Nenhum lead.")

    # ------------------ Processos ------------------
    elif escolha=="Processos":
        st.subheader("📄 Cadastro de Processos")
        with st.form("form_processo"):
            cli = st.text_input("Cliente*")
            num = st.text_input("Número*")
            tc = st.selectbox("Contrato*",["Fixo","Por Ato","Contingência"])
            desc = st.text_area("Descrição*")
            col1,col2 = st.columns(2)
            with col1:
                vt = st.number_input("Valor Total (R$)*",min_value=0.0,format="%.2f")
            with col2:
                vm = st.number_input("Valor Movimentado (R$)",min_value=0.0,format="%.2f")
            pi = st.date_input("Prazo Inicial*",value=datetime.date.today())
            pf = st.date_input("Prazo Final*",value=datetime.date.today()+datetime.timedelta(days=30))
            mov = st.checkbox("Houve movimentação?")
            area = st.selectbox("Área*",["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
            if area_u!="Todas":
                st.info(f"Área fixada: {area_u}"); area=area_u
            link = st.text_input("Link Material")
            encer = st.checkbox("Encerrado?")
            if st.form_submit_button("Salvar Processo"):
                if not all([cli,num,desc]):
                    st.warning("Campos obrigatórios!")
                else:
                    np = {
                        "cliente":cli,"numero":num,"contrato":tc,"descricao":desc,
                        "valor_total":vt,"valor_movimentado":vm,
                        "prazo_inicial":pi.strftime("%Y-%m-%d"),
                        "prazo":pf.strftime("%Y-%m-%d"),
                        "houve_movimentacao":mov,"encerrado":encer,
                        "escritorio":st.session_state.USERS[st.session_state.usuario].get("escritorio","Global"),
                        "area":area,"responsavel":st.session_state.usuario,
                        "link_material":link,
                        "data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    if enviar_dados_para_planilha("Processo",np):
                        PROCESSOS.append(np); st.success("Processo salvo!")

        st.subheader("Lista de Processos Cadastrados")
        if PROCESSOS:
            df = get_dataframe_with_cols(PROCESSOS,["numero","cliente","contrato","prazo","responsavel"])
            st.dataframe(df)
            c1,c2 = st.columns(2)
            with c1:
                if st.button("Exportar TXT"):
                    txt="\n".join(f"{p['cliente']} | {p['numero']} | {p['prazo']}" for p in PROCESSOS)
                    st.download_button("Baixar TXT",txt,file_name="processos.txt")
            with c2:
                if st.button("Exportar PDF"):
                    txt="\n".join(f"{p['cliente']} | {p['numero']} | {p['prazo']}" for p in PROCESSOS)
                    pdf=exportar_pdf(txt,"processos")
                    with open(pdf,"rb") as f: st.download_button("Baixar PDF",f,file_name=pdf)
        else:
            st.info("Nenhum processo.")

    # ------------------ Históricos ------------------
    elif escolha=="Históricos":
        st.subheader("📜 Histórico de Processos + Consulta TJMG")
        num = st.text_input("Número do processo")
        if num:
            hist = [h for h in HISTORICO_PETICOES if h.get("numero")==num]
            if hist:
                for item in hist:
                    with st.expander(f"{item['tipo']} - {item['data']}"):
                        st.write(f"**Responsável:** {item['responsavel']}")
                        st.write(f"**Conteúdo:** {item['conteudo']}")
            else:
                st.info("Nenhum histórico.")
        st.write("**Consulta TJMG**")
        iframe = """
<div style="overflow:auto;height:600px;">
  <iframe src="https://www.tjmg.jus.br/portal-tjmg/processos/andamento-processual/"
          style="width:100%;height:100%;border:none;" scrolling="yes">
  </iframe>
</div>"""
        st.components.v1.html(iframe,height=600)

    # ------------------ Relatórios ------------------
    elif escolha=="Relatórios":
        st.subheader("📊 Relatórios Personalizados")
        with st.expander("🔍 Filtros Avançados",expanded=True):
            with st.form("form_filtros"):
                c1,c2,c3 = st.columns(3)
                with c1:
                    tipo = st.selectbox("Tipo*",["Processos","Escritórios"])
                    if tipo=="Processos":
                        if area_u!="Todas":
                            area_filtro=area_u; st.info(f"Área fixa: {area_u}")
                        else:
                            area_filtro=st.selectbox("Área",["Todas"]+list({p["area"] for p in PROCESSOS}))
                    else:
                        area_filtro=None
                    status_filtro = st.selectbox("Status",["Todos","🔴 Atrasado","🟡 Atenção","🔵 Movimentado","⚫ Encerrado"])
                with c2:
                    esc_filtro = st.selectbox("Escritório",["Todos"]+list({p["escritorio"] for p in PROCESSOS}))
                    resp_filtro= st.selectbox("Responsável",["Todos"]+list({p["responsavel"] for p in PROCESSOS}))
                with c3:
                    dt_i = st.date_input("Data Início")
                    dt_f = st.date_input("Data Fim")
                    fmt  = st.selectbox("Formato",["PDF","DOCX","CSV"])
                if st.form_submit_button("Aplicar"):
                    filtros={}
                    if area_filtro and area_filtro!="Todas": filtros["area"]=area_filtro
                    if esc_filtro!="Todos": filtros["escritorio"]=esc_filtro
                    if resp_filtro!="Todos": filtros["responsavel"]=resp_filtro
                    if dt_i: filtros["data_inicio"]=dt_i
                    if dt_f: filtros["data_fim"]=dt_f
                    if tipo=="Processos":
                        dados = aplicar_filtros(PROCESSOS,filtros)
                        if status_filtro!="Todos":
                            if status_filtro=="⚫ Encerrado":
                                dados=[p for p in dados if p.get("encerrado",False)]
                            else:
                                dados=[p for p in dados if calcular_status_processo(converter_data(p.get("prazo")),p.get("houve_movimentacao",False),p.get("encerrado",False))==status_filtro]
                        st.session_state.dados_relatorio=dados; st.session_state.tipo_relatorio="Processos"
                    else:
                        dados=aplicar_filtros(ESCRITORIOS,filtros)
                        st.session_state.dados_relatorio=dados; st.session_state.tipo_relatorio="Escritórios"

        if st.session_state.get("dados_relatorio"):
            dr = st.session_state.dados_relatorio
            st.write(f"{st.session_state.tipo_relatorio}: {len(dr)}")
            if st.button(f"Exportar ({fmt})"):
                if fmt=="PDF":
                    arq = gerar_relatorio_pdf(dr) if st.session_state.tipo_relatorio=="Processos" else exportar_pdf(str(dr))
                elif fmt=="DOCX":
                    txt = "\n".join(f"{p['numero']} - {p['cliente']}" for p in dr) if st.session_state.tipo_relatorio=="Processos" else str(dr)
                    arq = exportar_docx(txt)
                else:
                    dfexp = pd.DataFrame(dr); csvb = dfexp.to_csv(index=False).encode("utf-8")
                    st.download_button("Baixar CSV",csvb,file_name=f"rel_{datetime.datetime.now().strftime('%Y%m%d')}.csv",mime="text/csv")
                    st.dataframe(dfexp); return
                with open(arq,"rb") as f:
                    st.download_button("Baixar "+fmt, f, file_name=arq)

    # ------------------ Gerenciar Funcionários ------------------
    elif escolha=="Gerenciar Funcionários":
        st.subheader("👥 Cadastro de Funcionários")
        with st.form("form_func"):
            nome   = st.text_input("Nome*")
            email  = st.text_input("E-mail*")
            tel    = st.text_input("Telefone*")
            usr    = st.text_input("Usuário*")
            pwd    = st.text_input("Senha*",type="password")
            esc    = st.selectbox("Escritório",[e["nome"] for e in ESCRITORIOS] or ["Global"])
            area_f = st.selectbox("Área",["Cível","Criminal","Trabalhista","Previdenciário","Tributário","Todas"])
            papel_f= st.selectbox("Papel",["manager","lawyer","assistant"])
            if st.form_submit_button("Cadastrar"):
                if not all([nome,email,tel,usr,pwd]):
                    st.warning("Campos obrigatórios!")
                else:
                    nf = {
                        "nome":nome,"email":email,"telefone":tel,
                        "usuario":usr,"senha":pwd,
                        "escritorio":esc,"area":area_f,"papel":papel_f,
                        "data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "cadastrado_por":st.session_state.usuario
                    }
                    if enviar_dados_para_planilha("Funcionario",nf):
                        st.success("Funcionario cadastrado!")
                        FUNCIONARIOS[:] = carregar_dados_da_planilha("Funcionario") or []

        st.subheader("Lista de Funcionários")
        if FUNCIONARIOS:
            if papel=="manager":
                vis = [f for f in FUNCIONARIOS if f.get("escritorio")==esc_u]
            else:
                vis = FUNCIONARIOS
            if vis:
                df = get_dataframe_with_cols(vis,["nome","email","telefone","usuario","papel","escritorio","area"])
                st.dataframe(df)
                c1,c2 = st.columns(2)
                with c1:
                    if st.button("TXT Funcionários"):
                        txt="\n".join(f"{f['nome']} | {f['email']} | {f['telefone']}" for f in vis)
                        st.download_button("Baixar TXT",txt,file_name="funcionarios.txt")
                with c2:
                    if st.button("PDF Funcionários"):
                        txt="\n".join(f"{f['nome']} | {f['email']} | {f['telefone']}" for f in vis)
                        pdf=exportar_pdf(txt,"funcionarios")
                        with open(pdf,"rb") as fp: st.download_button("Baixar PDF",fp,file_name=pdf)
            else:
                st.info("Nenhum funcionário.")

    # ------------------ Gerenciar Escritórios ------------------
    elif escolha=="Gerenciar Escritórios" and papel=="owner":
        st.subheader("🏢 Gerenciamento de Escritórios")
        tab1,tab2,tab3 = st.tabs(["Cadastrar","Lista","Administradores"])
        with tab1:
            with st.form("form_esc"):
                nome = st.text_input("Nome*")
                end  = st.text_input("Endereço*")
                tel  = st.text_input("Telefone*")
                email= st.text_input("E-mail*")
                cnpj = st.text_input("CNPJ*")
                st.subheader("Resp. Técnico")
                resp = st.text_input("Nome*")
                telr = st.text_input("Telefone*")
                emailr = st.text_input("E-mail*")
                areas= st.multiselect("Áreas",["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
                if st.form_submit_button("Salvar Escritório"):
                    campos=[nome,end,tel,email,cnpj,resp,telr,emailr]
                    if not all(campos):
                        st.warning("Preencha todos!")
                    else:
                        ne = {
                            "nome":nome,"endereco":end,"telefone":tel,"email":email,
                            "cnpj":cnpj,"data_cadastro":datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "responsavel":st.session_state.usuario,
                            "responsavel_tecnico":resp,"telefone_tecnico":telr,"email_tecnico":emailr,
                            "area_atuacao":", ".join(areas)
                        }
                        if enviar_dados_para_planilha("Escritorio",ne):
                            ESCRITORIOS.append(ne); st.success("Salvo!")

        with tab2:
            st.subheader("Lista de Escritórios")
            if ESCRITORIOS:
                df = get_dataframe_with_cols(ESCRITORIOS,["nome","endereco","telefone","email","cnpj"])
                st.dataframe(df)
                c1,c2=st.columns(2)
                with c1:
                    if st.button("TXT Escritórios"):
                        txt="\n".join(f"{e['nome']} | {e['endereco']} | {e['telefone']}" for e in ESCRITORIOS)
                        st.download_button("Baixar TXT",txt,file_name="escritorios.txt")
                with c2:
                    if st.button("PDF Escritórios"):
                        txt="\n".join(f"{e['nome']} | {e['endereco']} | {e['telefone']}" for e in ESCRITORIOS)
                        pdf=exportar_pdf(txt,"escritorios")
                        with open(pdf,"rb") as f: st.download_button("Baixar PDF",f,file_name=pdf)
            else:
                st.info("Nenhum escritório.")

        with tab3:
            st.subheader("Administradores")
            st.info("Funcionalidade em desenvolvimento.")

    # ------------------ Gerenciar Permissões ------------------
    elif escolha=="Gerenciar Permissões" and papel=="owner":
        st.subheader("🔧 Gerenciar Permissões")
        if FUNCIONARIOS:
            df = pd.DataFrame(FUNCIONARIOS)
            st.dataframe(df)
            sel = st.selectbox("Funcionário",df["nome"].tolist())
            novas = st.multiselect("Áreas Permitidas",["Cível","Criminal","Trabalhista","Previdenciário","Tributário"])
            if st.button("Atualizar"):
                ok=False
                for i,f in enumerate(FUNCIONARIOS):
                    if f.get("nome")==sel:
                        FUNCIONARIOS[i]["area"] = ", ".join(novas); ok=True
                        for k,u in st.session_state.USERS.items():
                            if u.get("username")==f.get("usuario"):
                                st.session_state.USERS[k]["area"] = ", ".join(novas)
                if ok and enviar_dados_para_planilha("Funcionario",{"nome":sel,"area":", ".join(novas),"atualizar":True}):
                    st.success("Permissões atualizadas!")
                else:
                    st.error("Falha ao atualizar.")
        else:
            st.info("Nenhum funcionário.")

if __name__ == '__main__':
    main()
