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
import streamlit.components.v1 as components

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
        if not key:
            continue
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


def consultar_movimentacoes_simples(numero_processo):
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={numero_processo}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        andamentos = soup.find_all("tr", class_="fundocinza1")
        return [a.get_text(strip=True) for a in andamentos[:5]] if andamentos else ["Nenhuma movimentação encontrada"]
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
    headers = ["Cliente", "Número", "Área", "Status", "Responsável"]
    widths = [40, 30, 50, 30, 40]
    for h, w in zip(headers, widths): pdf.cell(w, 10, txt=h, border=1)
    pdf.ln()
    for p in dados:
        status = calcular_status_processo(converter_data(p.get("prazo")), p.get("houve_movimentacao", False), p.get("encerrado", False))
        cols = [p.get("cliente", ""), p.get("numero", ""), p.get("area", ""), status, p.get("responsavel", "")]
        for v, w in zip(cols, widths): pdf.cell(w, 10, txt=str(v), border=1)
        pdf.ln()
    pdf.output(f"{nome_arquivo}.pdf")
    return f"{nome_arquivo}.pdf"


def aplicar_filtros(dados, filtros):
    def extrar(r):
        ds = r.get("data_cadastro") or r.get("cadastro")
        return None if not ds else datetime.date.fromisoformat(ds[:10])
    res = []
    for r in dados:
        ok, dr = True, extrar(r)
        for c, v in filtros.items():
            if not v: continue
            if c == "data_inicio" and (dr is None or dr < v): ok = False; break
            if c == "data_fim" and (dr is None or dr > v): ok = False; break
            if c not in ["data_inicio", "data_fim"] and v.lower() not in str(r.get(c, "")).lower(): ok = False; break
        if ok: res.append(r)
    return res


def atualizar_processo(numero_processo, atualizacoes):
    atualizacoes["numero"] = numero_processo; atualizacoes["atualizar"] = True
    return enviar_dados_para_planilha("Processo", atualizacoes)


def excluir_processo(numero_processo):
    return enviar_dados_para_planilha("Processo", {"numero": numero_processo, "excluir": True})


def get_dataframe_with_cols(data, cols):
    df = pd.DataFrame(data if isinstance(data, list) else [data])
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

    # Sidebar: Login/Logout
    with st.sidebar:
        st.header("🔐 Login")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = login(usuario, senha)
            if user:
                st.session_state.usuario = usuario; st.session_state.papel = user.get("papel"); st.session_state.dados_usuario = user; st.success("Login realizado com sucesso!")
            else: st.error("Credenciais inválidas")
        if st.session_state.get("usuario") and st.button("Sair"):
            for k in ["usuario","papel","dados_usuario"]: st.session_state.pop(k, None)
            st.sidebar.success("Você saiu do sistema!"); st.experimental_rerun()

    if not st.session_state.get("usuario"):
        st.info("Por favor, faça login para acessar o sistema.")
        return

    papel = st.session_state.papel
    escritorio_usuario = st.session_state.dados_usuario.get("escritorio", "Global")
    area_usuario = st.session_state.dados_usuario.get("area", "Todas")
    st.sidebar.success(f"Bem-vindo, {st.session_state.usuario} ({papel})")

    # Menu
    menu = ["Dashboard", "Clientes", "Gestão de Leads", "Processos", "Históricos"]
    if papel in ["owner", "manager"]: menu.append("Relatórios")
    if papel == "manager": menu.append("Gerenciar Funcionários")
    if papel == "owner": menu.extend(["Gerenciar Escritórios", "Gerenciar Permissões"] )
    escolha = st.sidebar.selectbox("Menu", menu)

    # ---- Dashboard ----
    if escolha == "Dashboard":
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
        pass
    # ---- Clientes ----
    elif escolha == "Clientes":
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
        pass
    # ---- Gestão de Leads ----
    elif escolha == "Gestão de Leads":
       elif escolha == "Gestão de Leads":
            st.subheader("📇 Gestão de Leads")
            with st.form("form_lead"):
                nome = st.text_input("Nome*", key="nome_lead")
                contato = st.text_input("Contato*")
                email = st.text_input("E-mail*")
                data_aniversario = st.date_input("Data de Aniversário")
                if st.form_submit_button("Salvar Lead"):
                    if not nome or not contato or not email:
                        st.warning("Preencha todos os campos obrigatórios!")
                    else:
                        # Montamos o dicionário que será enviado para a aba "Lead"
                        novo_lead = {
                            "nome": nome,
                            "numero": contato,
                            "tipo_email": email,
                            "data_aniversario": data_aniversario.strftime("%Y-%m-%d"),
                            "origem": "lead",  # se desejar manter esse campo
                            "data_cadastro": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        # Enviando diretamente para a aba "Lead"
                        if enviar_dados_para_planilha("Lead", novo_lead):
                            # Recarrega os leads após envio
                            LEADS = carregar_dados_da_planilha("Lead") or []
                            st.success("Lead cadastrado com sucesso!")
        pass
    # ---- Processos ----
    elif escolha == "Processos":
        elif escolha == "Processos":
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
                link_material = st.text_input("Link do Material Complementar (opcional)")
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
                            "prazo": prazo_final.strftime("%Y-%m-%d"),
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
        pass
    # ---- Históricos ----
    elif escolha == "Históricos":
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
        pass
    # ---- Relatórios ----
    elif escolha == "Relatórios" and papel in ["owner", "manager"]:
         elif escolha == "Relatórios":
            st.subheader("📊 Relatórios Personalizados")
            with st.expander("🔍 Filtros Avançados", expanded=True):
                with st.form("form_filtros"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        tipo_relatorio = st.selectbox("Tipo de Relatório*", ["Processos", "Escritórios"])
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
                        formato_exportacao = st.selectbox("Formato de Exportação", ["PDF", "DOCX", "CSV"])
                    
                    if st.form_submit_button("Aplicar Filtros"):
                        # Monta o dicionário de filtros
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
        pass
    # ---- Gerenciar Funcionários ----
    elif escolha == "Gerenciar Funcionários":
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
                            st.session_state.USERS = carregar_usuarios_da_planilha()
        pass
    # ---- Gerenciar Escritórios ----
    elif escolha == "Gerenciar Escritórios" and papel == "owner":
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
                            nome, endereco, telefone, email,
                            cnpj, responsavel_tecnico, telefone_tecnico, email_tecnico
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
                            txt_exp = "\n".join([
                                f'{e.get("nome", "")} | {e.get("endereco", "")} | {e.get("telefone", "")}'
                                for e in ESCRITORIOS
                            ])
                            pdf_file = exportar_pdf(txt_exp, nome_arquivo="escritorios")
                            with open(pdf_file, "rb") as f:
                                st.download_button("Baixar PDF", f, file_name=pdf_file)
                else:
                    st.info("Nenhum escritório cadastrado ainda")
            
            with tab3:
                st.subheader("Administradores de Escritórios")
                st.info("Aqui será possível cadastrar advogados administradores para cada escritório (funcionalidade em desenvolvimento).")
        pass
    # ---- Gerenciar Permissões ----
    elif escolha == "Gerenciar Permissões" and papel == "owner":
        elif escolha == "Gerenciar Permissões" and papel == "owner":
            st.subheader("🔧 Gerenciar Permissões de Funcionários")
            st.info("Configure as áreas de atuação do funcionário (limitando acesso a relatórios, clientes, processos e escritórios).")
            if FUNCIONARIOS:
                df_func = pd.DataFrame(FUNCIONARIOS)
                st.dataframe(df_func)
                funcionario_selecionado = st.selectbox("Funcionário", df_func["nome"].tolist())
                novas_areas = st.multiselect("Áreas Permitidas", ["Cível", "Criminal", "Trabalhista", "Previdenciário", "Tributário"])
                if st.button("Atualizar Permissões"):
                    atualizado = False
                    for idx, func in enumerate(FUNCIONARIOS):
                        # Verifica se o "nome" corresponde ao funcionário selecionado
                        if func.get("nome") == funcionario_selecionado:
                            FUNCIONARIOS[idx]["area"] = ", ".join(novas_areas)
                            atualizado = True
                            # Atualiza no dicionário de usuários também
                            for key, user in st.session_state.USERS.items():
                                if user.get("username") == func.get("usuario"):
                                    st.session_state.USERS[key]["area"] = ", ".join(novas_areas)
                    
                    if atualizado:
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

        pass

if __name__ == "__main__":
    main()
