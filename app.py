import streamlit as st
import datetime
import httpx
import requests
import pandas as pd
from dotenv import load_dotenv
import os
from fpdf import FPDF
from docx import Document

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
        data_str = data_str.replace("Z", "")
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
        users["dono"] = {"username": "dono", "senha": "dono123", "papel": "owner"}
        return users
    for f in funcs:
        u = f.get("usuario")
        if not u:
            continue
        users[u] = {
            "username": u,
            "senha": f.get("senha", ""),
            "papel": f.get("papel", "assistant"),
            "escritorio": f.get("escritorio", "Global"),
            "area": f.get("area", "Todas")
        }
    return users


def login(usuario, senha):
    user = st.session_state.USERS.get(usuario)
    if user and user["senha"] == senha:
        return user
    return None


def calcular_status_processo(data_prazo, mov, encerrado=False):
    if encerrado:
        return "⚫ Encerrado"
    hoje = datetime.date.today()
    dias = (data_prazo - hoje).days
    if mov:
        return "🔵 Movimentado"
    if dias < 0:
        return "🔴 Atrasado"
    if dias <= 10:
        return "🟡 Atenção"
    return "🟢 Normal"


def exportar_pdf(texto, nome_arquivo="relatorio"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, texto)
    caminho = f"{nome_arquivo}.pdf"
    pdf.output(caminho)
    return caminho


def exportar_docx(texto, nome_arquivo="relatorio"):
    doc = Document()
    for linha in texto.split("\n"):
        doc.add_paragraph(linha)
    caminho = f"{nome_arquivo}.docx"
    doc.save(caminho)
    return caminho


def get_dataframe_with_cols(data, cols):
    if isinstance(data, dict):
        data = [data]
    df = pd.DataFrame(data)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols]


def aplicar_filtros(data, filtros):
    resultado = []
    for item in data:
        ok = True
        # Filtro por área
        area = filtros.get("area")
        if area and area not in ("Todas", "Todos"):
            if item.get("area") != area:
                ok = False
        # Filtro por escritório
        esc = filtros.get("escritorio")
        if esc and esc not in ("Todas", "Todos"):
            if item.get("escritorio") != esc:
                ok = False
        # Filtro por responsável
        resp = filtros.get("responsavel")
        if resp and resp not in ("Todas", "Todos"):
            if item.get("responsavel") != resp:
                ok = False
        if not ok:
            continue
        # Filtro por datas
        data_inicio = filtros.get("data_inicio")
        data_fim = filtros.get("data_fim")
        campo_data = item.get("data_cadastro") or item.get("prazo")
        dt = converter_data(campo_data)
        if data_inicio and dt < data_inicio:
            continue
        if data_fim and dt > data_fim:
            continue
        resultado.append(item)
    return resultado


##############################
# Interface Principal
##############################
def main():
    st.title("Sistema Jurídico")
    # Atualiza usuários
    st.session_state.USERS = carregar_usuarios_da_planilha()

    # Carrega dados
    CLIENTES = carregar_dados_da_planilha("Cliente") or []
    PROCESSOS = carregar_dados_da_planilha("Processo") or []
    ESCRITORIOS = carregar_dados_da_planilha("Escritorio") or []
    HIST_PETICOES = carregar_dados_da_planilha("Historico_Peticao") or []
    if not isinstance(HIST_PETICOES, list):
        HIST_PETICOES = []
    FUNCIONARIOS = carregar_dados_da_planilha("Funcionario") or []

    # Gera lista de Leads a partir dos clientes
    LEADS = [c for c in CLIENTES if c.get("tipo_cliente") == "Lead"]

    # Sidebar: login
    with st.sidebar:
        st.header("🔐 Login")
        usuario_input = st.text_input("Usuário")
        senha_input = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            usr = login(usuario_input, senha_input)
            if usr:
                st.session_state.usuario = usuario_input
                st.session_state.papel = usr["papel"]
                st.session_state.dados_usuario = usr
                st.success("Login ok!")
            else:
                st.error("Credenciais inválidas")
    if "usuario" in st.session_state:
        if st.sidebar.button("Sair"):
            for chave in ["usuario", "papel", "dados_usuario"]:
                st.session_state.pop(chave, None)
            st.sidebar.success("Você saiu")
            st.experimental_rerun()

    # Verifica login
    if "usuario" not in st.session_state:
        st.info("Faça login para acessar")
        return

    papel = st.session_state.papel
    esc_user = st.session_state.dados_usuario.get("escritorio", "Global")
    area_user = st.session_state.dados_usuario.get("area", "Todas")
    st.sidebar.success(f"{st.session_state.usuario} ({papel})")

    # Menu
    ops = ["Dashboard", "Clientes", "Processos", "Históricos", "Relatórios", "Gerenciar Funcionários"]
    if papel == "owner":
        ops += ["Gerenciar Escritórios", "Gerenciar Permissões"]
    escolha = st.sidebar.selectbox("Menu", ops)

    # ------------------ Dashboard ------------------
    if escolha == "Dashboard":
        st.subheader("📋 Painel de Controle")
        with st.expander("🔍 Filtros", expanded=True):
                col1, col2, col3 = st.columns(3)
                if area_fixa:
                    st.info(f"Filtrando pela área: {area_fixa}")
                    filtro_area = area_fixa
                else:
                    filtro_area = st.selectbox("Área", ["Todas"] + list(set(p["area"] for p in PROCESSOS)))
                filtro_status = st.selectbox("Status", ["Todos", "🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado", "⚫ Encerrado"])
                filtro_escritorio = st.selectbox("Escritório", ["Todos"] + list(set(p["escritorio"] for p in PROCESSOS)))
            
            # Aplica filtros no PROCESSOS
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
            
            # Exibição dos aniversariantes do dia (baseado na aba Cliente)
            hoje = datetime.date.today()
            aniversariantes = []
            for cliente in CLIENTES:
                data_str = cliente.get("aniversario", "")
                try:
                    data_aniversario = datetime.datetime.strptime(data_str, "%Y-%m-%d").date()
                    if data_aniversario.month == hoje.month and data_aniversario.day == hoje.day:
                        aniversariantes.append(cliente)
                except Exception:
                    continue
            st.markdown("### 🎂 Aniversariantes do Dia")
            if aniversariantes:
                for a in aniversariantes:
                    st.write(f"{a.get('nome', 'N/A')} - {a.get('aniversario', '')}")
            else:
                st.info("Nenhum aniversariante para hoje.")
            
            # Gráfico de Pizza com as cores definidas
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
                # Ordena pelo status
                status_order = {"🔴 Atrasado": 0, "🟡 Atenção": 1, "🟢 Normal": 2, "🔵 Movimentado": 3, "⚫ Encerrado": 4}
                df_proc['Status_Order'] = df_proc['Status'].map(status_order)
                df_proc = df_proc.sort_values('Status_Order').drop('Status_Order', axis=1)
                # Converte o link em hiperlink clicável
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
                    novo_link = st.text_input("Link do Material Complementar (opcional)", value=processo_alvo.get("link_material", ""))
                    if processo_alvo.get("link_material"):
                        st.markdown(f"[Abrir Material]({processo_alvo.get('link_material')})")
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
    elif escolha == "Processos":
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
    elif escolha == "Históricos":
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

    # ------------------ Relatórios ------------------
    elif escolha == "Relatórios":
        st.subheader("📊 Relatórios Personalizados")
        with st.expander("🔍 Filtros Avançados", expanded=True):
            with st.form("form_filtros"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    tipo_rel = st.selectbox("Tipo de Relatório*", ["Processos", "Escritórios", "Leads"])
                    if tipo_rel == "Processos":
                        if area_user and area_user != "Todas":
                            area_filtro = area_user
                            st.info(f"Filtrando pela área: {area_user}")
                        else:
                            area_filtro = st.selectbox("Área", ["Todas"] + sorted({p.get("area") for p in PROCESSOS}))
                    else:
                        area_filtro = None
                    status_filtro = st.selectbox("Status", ["Todos", "🔴 Atrasado", "🟡 Atenção", "🟢 Normal", "🔵 Movimentado", "⚫ Encerrado"])
                with col2:
                    esc_filtro = st.selectbox("Escritório", ["Todos"] + sorted({p.get("escritorio") for p in PROCESSOS}))
                    resp_filtro = st.selectbox("Responsável", ["Todos"] + sorted({p.get("responsavel") for p in PROCESSOS}))
                with col3:
                    data_inicio = st.date_input("Data Início")
                    data_fim = st.date_input("Data Fim")
                    fmt_export = st.selectbox("Formato de Exportação", ["PDF", "DOCX", "CSV", "TXT"])
                if st.form_submit_button("Aplicar Filtros"):
                    filtros = {
                        "area": area_filtro,
                        "escritorio": esc_filtro,
                        "responsavel": resp_filtro,
                        "data_inicio": data_inicio,
                        "data_fim": data_fim
                    }
                    if tipo_rel == "Processos":
                        dados_fil = aplicar_filtros(PROCESSOS, filtros)
                    elif tipo_rel == "Escritórios":
                        dados_fil = aplicar_filtros(ESCRITORIOS, filtros)
                    else:
                        dados_fil = LEADS
                    # Aplica status se necessário
                    if tipo_rel == "Processos" and status_filtro != "Todos":
                        if status_filtro == "⚫ Encerrado":
                            dados_fil = [p for p in dados_fil if p.get("encerrado")]
                        else:
                            dados_fil = [p for p in dados_fil if calcular_status_processo(
                                converter_data(p.get("prazo")), p.get("houve_movimentacao", False), p.get("encerrado", False)
                            ) == status_filtro]
                    st.session_state.dados_relatorio = dados_fil
                    st.session_state.tipo_relatorio = tipo_rel
        # Exibe e exporta
        if "dados_relatorio" in st.session_state and st.session_state.dados_relatorio:
            st.write(f"{st.session_state.tipo_relatorio} encontrados: {len(st.session_state.dados_relatorio)}")
            if st.button(f"Exportar Relatório ({fmt_export})"):
                dados = st.session_state.dados_relatorio
                if fmt_export == "PDF":
                    texto = "\n".join(
                        f"{d.get('numero','')} | {d.get('cliente','')} | {d.get('area','')}" for d in dados
                    )
                    arquivo = exportar_pdf(texto, nome_arquivo=f"relatorio_{st.session_state.tipo_relatorio.lower()}")
                    with open(arquivo, "rb") as f:
                        st.download_button("Baixar PDF", f, file_name=arquivo)
                elif fmt_export == "DOCX":
                    texto = "\n".join(
                        str(d) for d in dados
                    )
                    arquivo = exportar_docx(texto, nome_arquivo=f"relatorio_{st.session_state.tipo_relatorio.lower()}")
                    with open(arquivo, "rb") as f:
                        st.download_button("Baixar DOCX", f, file_name=arquivo)
                elif fmt_export == "CSV":
                    df = pd.DataFrame(dados)
                    csv_bytes = df.to_csv(index=False).encode("utf-8")
                    st.download_button("Baixar CSV", data=csv_bytes, file_name=f"relatorio_{datetime.datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
                else:  # TXT
                    txt = "\n".join(str(d) for d in dados)
                    st.download_button("Baixar TXT", data=txt, file_name=f"relatorio_{st.session_state.tipo_relatorio.lower()}.txt")

    # ------------------ Gerenciar Funcionários ------------------
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

    # ------------------ Gerenciar Escritórios ------------------
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

    # ------------------ Gerenciar Permissões ------------------
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

    else:
        st.info("Por favor, faça login para acessar o sistema.")

if __name__ == '__main__':
    main()
