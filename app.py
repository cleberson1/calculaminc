import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO E SUPORTE ---
st.set_page_config(page_title="Simulador Salarial IPHAN", layout="wide", page_icon="🏛️")

def formatar_br(valor):
    """Formata valores para o padrão brasileiro R$ 1.234,56"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(valor):
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try: return float(v)
        except: return 0.0
    return float(valor) if valor is not None else 0.0

# --- 2. CÁLCULO TRIBUTÁRIO (LEI 15.270/2025) ---

def calcular_irpf(base_mensal, cenario_nome):
    # Tabela Progressiva
    if base_mensal <= 2259.20: bruto, aliq = 0.0, 0.0
    elif base_mensal <= 2828.65: bruto, aliq = (base_mensal * 0.075) - 169.44, 7.5
    elif base_mensal <= 3751.05: bruto, aliq = (base_mensal * 0.15) - 381.44, 15.0
    elif base_mensal <= 4664.68: bruto, aliq = (base_mensal * 0.225) - 662.77, 22.5
    else: bruto, aliq = (base_mensal * 0.275) - 896.00, 27.5

    # Redução Art. 3º-A (Cenários de 2026)
    reducao = 0.0
    if "2026" in cenario_nome or "PL" in cenario_nome:
        if base_mensal <= 5000.00: reducao = min(312.89, bruto)
        elif base_mensal <= 7350.00: reducao = max(0.0, min(978.62 - (0.133145 * base_mensal), bruto))

    return max(0.0, bruto - reducao), aliq, reducao

# --- 3. CARREGAMENTO DOS DADOS ---

@st.cache_data
def carregar_dados():
    niveis = {"SUPERIOR": "superior", "INTERMEDIÁRIO": "intermediario", "AUXILIAR": "auxiliar"}
    sufixos = {"-2026": "Vigente 2026", "-PL": "Proposta PL"}
    dfs = []
    for nome_n, prefixo in niveis.items():
        for suf, cenario in sufixos.items():
            path = f"tabela_{prefixo}{suf}.csv"
            if os.path.exists(path):
                df = pd.read_csv(path, sep=';', encoding='utf-8-sig')
                df['nivel_ref'] = nome_n
                df['cenario_ref'] = cenario
                for col in ['vb', 'gdac_80', 'gdac_100', 'gdac_50']:
                    if col in df.columns: df[col] = df[col].apply(limpar_valor)
                dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else None

df_total = carregar_dados()

# --- 4. BARRA LATERAL (CONFIGURAÇÃO GLOBAL) ---

st.sidebar.header("⚙️ Configurações Gerais")
vinculo = st.sidebar.radio("Situação do Servidor", ["Ativo", "Aposentado/Pensionista"])
nivel_sel = st.sidebar.selectbox("Nível do Cargo", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])

df_f = df_total[df_total['nivel_ref'] == nivel_sel]
classe_sel = st.sidebar.selectbox("Classe", sorted(df_f['classe'].unique(), reverse=True))
padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_f[df_f['classe'] == classe_sel]['padrao'].unique()))

st.sidebar.markdown("---")
st.sidebar.subheader("Rubricas Adicionais")
# Campos com ponto para entrada, mas que serão formatados com vírgula na exibição
func = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=0.01, format="%.2f")
saude = st.sidebar.number_input("Ressarcimento Saúde (Per Capita)", min_value=0.0, step=0.01, format="%.2f")

pre = 0.0
if vinculo == "Ativo":
    pontos = st.sidebar.select_slider("Pontos GDAC", [80, 100], 100)
    if st.sidebar.checkbox("Auxílio Pré-Escolar (+ R$ 321,00)"): pre = 321.0
else:
    pontos = 50
    st.sidebar.info("Aposentadoria: GDAC fixada em 50 pontos.")

# --- 5. PROCESSAMENTO DOS CENÁRIOS ---

def calcular_cenario(cenario_nome):
    try:
        dados = df_f[(df_f['cenario_ref'] == cenario_nome) &
                     (df_f['classe'] == classe_sel) &
                     (df_f['padrao'] == padrao_sel)].iloc[0]
        vb = dados['vb']
        if vinculo == "Ativo":
            gdac = dados['gdac_80'] if pontos == 80 else dados['gdac_100']
            alim = 1175.0
        else:
            gdac = dados.get('gdac_50', dados['gdac_100'] * 0.5)
            alim = 0.0

        base_tributavel = vb + gdac + func
        ir, aliq, red = calcular_irpf(base_tributavel, cenario_nome)
        bruto = vb + gdac + alim + func + pre + saude
        liquido = bruto - ir

        return {"VB": vb, "GDAC": gdac, "ALIM": alim, "FUNC": func, "PRE": pre,
                "SAUDE": saude, "BRUTO": bruto, "IR": ir, "LIQ": liquido, "RED": red, "ALIQ": aliq}
    except: return None

res_vig = calcular_cenario("Vigente 2026")
res_pl = calcular_cenario("Proposta PL")

# --- 6. INTERFACE PRINCIPAL (ABAS) ---

st.title("📊 Simulador Salarial MINC/IPHAN")

if res_vig and res_pl:
    # Criação das Abas
    tab1, tab2 = st.tabs(["🎯 Calculadora Individual", "⚖️ Quadro Comparativo"])

    with tab1:
        st.subheader("Simulação de Recebimento Mensal")
        cenario_view = st.selectbox("Escolha o cenário para detalhamento:", ["Proposta PL", "Vigente 2026"])
        res = res_pl if cenario_view == "Proposta PL" else res_vig

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Bruto", f"R$ {formatar_br(res['BRUTO'])}")
        m2.metric("IRPF (com redução)", f"R$ {formatar_br(res['IR'])}",
                  delta=f"- R$ {formatar_br(res['RED'])}" if res['RED'] > 0 else None, delta_color="inverse")
        m3.metric("Líquido Estimado", f"R$ {formatar_br(res['LIQ'])}")

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Composição do Bruto")
            st.write(f"Vencimento Básico: **R$ {formatar_br(res['VB'])}**")
            st.write(f"GDAC ({pontos} pts): **R$ {formatar_br(res['GDAC'])}**")
            if res['ALIM'] > 0: st.write(f"Auxílio Alimentação: **R$ {formatar_br(res['ALIM'])}**")
            if func > 0: st.write(f"Função Comissionada: **R$ {formatar_br(func)}**")
            if pre > 0: st.success(f"Auxílio Pré-Escolar: **R$ {formatar_br(pre)}**")
            if saude > 0: st.write(f"Ressarcimento Saúde: **R$ {formatar_br(saude)}**")

        with c2:
            st.markdown("#### Retenções e Regras")
            st.write(f"Alíquota Aplicada: **{res['ALIQ']}%**")
            if res['RED'] > 0:
                st.info(f"Redução Lei 15.270 aplicada: **R$ {formatar_br(res['RED'])}**")
            else:
                st.write("Sem reduções adicionais aplicáveis.")

    with tab2:
        st.subheader("Comparativo Direto: Vigente vs. Proposta")

        dados_comp = [
            ["Vencimento Básico", formatar_br(res_vig['VB']), formatar_br(res_pl['VB'])],
            [f"GDAC ({pontos} pts)", formatar_br(res_vig['GDAC']), formatar_br(res_pl['GDAC'])],
            ["Auxílio Alimentação", formatar_br(res_vig['ALIM']), formatar_br(res_pl['ALIM'])],
            ["Função Comissionada", formatar_br(res_vig['FUNC']), formatar_br(res_pl['FUNC'])],
            ["Auxílio Pré-Escolar", formatar_br(res_vig['PRE']), formatar_br(res_pl['PRE'])],
            ["Ressarcimento Saúde", formatar_br(res_vig['SAUDE']), formatar_br(res_pl['SAUDE'])],
            ["---", "---", "---"],
            ["TOTAL BRUTO", f"**{formatar_br(res_vig['BRUTO'])}**", f"**{formatar_br(res_pl['BRUTO'])}**"],
            ["IRPF (Estimado)", f"- {formatar_br(res_vig['IR'])}", f"- {formatar_br(res_pl['IR'])}"],
            ["LÍQUIDO FINAL", f"**{formatar_br(res_vig['LIQ'])}**", f"**{formatar_br(res_pl['LIQ'])}**"]
        ]

        df_comp = pd.DataFrame(dados_comp, columns=["Rubrica", "Vigente (Abril/2026)", "Proposta (PL 5874)"])
        st.table(df_comp)

        ganho_real = res_pl['LIQ'] - res_vig['LIQ']
        st.success(f"✨ **Aumento no valor líquido:** R$ {formatar_br(ganho_real)} mensais.")

else:
    st.warning("Selecione os dados na barra lateral para carregar as tabelas.")

st.markdown("---")
st.caption("Nota: Este simulador é uma ferramenta de apoio. Os valores reais podem variar conforme consignações e descontos individuais (PSS, etc).")
