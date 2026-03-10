import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO E IDENTIDADE ---
st.set_page_config(page_title="Simulador Salarial MinC", layout="wide", page_icon="🏛️")

st.title("🏛️ Simulador Salarial MinC")

def formatar_br(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(valor):
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try: return float(v)
        except: return 0.0
    return float(valor) if valor is not None else 0.0

# --- 2. MOTOR DE CÁLCULO ---

def calcular_pss(base_contribuicao, vinculo):
    teto_rgps = 8157.41
    if vinculo != "Ativo":
        if base_contribuicao <= teto_rgps: return 0.0
        base_calculo = base_contribuicao - teto_rgps
    else:
        base_calculo = base_contribuicao

    faixas = [
        (1518.00, 0.075), (2793.88, 0.09), (4190.83, 0.12), (8157.41, 0.14),
        (13969.49, 0.145), (27938.95, 0.165), (54480.97, 0.19), (float('inf'), 0.22)
    ]
    
    total_pss = 0.0
    limite_anterior = 0.0
    for limite, aliquota in faixas:
        if base_calculo > limite_anterior:
            base_na_faixa = min(base_calculo, limite) - limite_anterior
            total_pss += base_na_faixa * aliquota
            limite_anterior = limite
        else: break
    return total_pss

def calcular_irpf(base_tributavel, cenario_nome, pss_pago, num_dependentes):
    """
    Cálculo do IRPF deduzindo PSS e Dependentes da base.
    """
    # Dedução por dependente (Valor padrão RFB)
    deducao_dependentes = num_dependentes * 189.59
    
    # A base de cálculo real é: Base Tributável - PSS - Dependentes
    base_liquida = max(0.0, base_tributavel - pss_pago - deducao_dependentes)
    
    if base_liquida <= 2259.20: bruto, aliq = 0.0, 0.0
    elif base_liquida <= 2828.65: bruto, aliq = (base_liquida * 0.075) - 169.44, 7.5
    elif base_liquida <= 3751.05: bruto, aliq = (base_liquida * 0.15) - 381.44, 15.0
    elif base_liquida <= 4664.68: bruto, aliq = (base_liquida * 0.225) - 662.77, 22.5
    else: bruto, aliq = (base_liquida * 0.275) - 896.00, 27.5
    
    reducao_social = 0.0
    if "2026" in cenario_nome or "PL" in cenario_nome:
        if base_liquida <= 5000.00: reducao_social = min(312.89, bruto)
        elif base_liquida <= 7350.00: reducao_social = max(0.0, min(978.62 - (0.133145 * base_liquida), bruto))
    
    return max(0.0, bruto - reducao_social), aliq, reducao_social, base_liquida

# --- 3. CARREGAMENTO ---
@st.cache_data
def carregar_dados():
    niveis = {"SUPERIOR": "superior", "INTERMEDIÁRIO": "intermediario", "AUXILIAR": "auxiliar"}
    sufixos = {"-2025": "Tabela Vigente 01/01/2025", "-2026": "Tabela Vigente 01/04/2026", "-PL": "Proposta PL 01/04/2026"}
    dfs = []
    for nome_n, prefixo in niveis.items():
        for suf, cenario in sufixos.items():
            path = f"tabela_{prefixo}{suf}.csv"
            if os.path.exists(path):
                df = pd.read_csv(path, sep=';', encoding='utf-8-sig')
                df['nivel_ref'], df['cenario_ref'] = nome_n, cenario
                for col in ['vb', 'gdac_80', 'gdac_100', 'gdac_50']:
                    if col in df.columns: df[col] = df[col].apply(limpar_valor)
                dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else None

df_total = carregar_dados()

if df_total is not None:
    # --- 4. PARÂMETROS ---
    st.sidebar.header("⚙️ Parâmetros")
    vinculo = st.sidebar.radio("Situação", ["Ativo", "Aposentado/Pensionista"])
    nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])
    
    df_nivel = df_total[df_total['nivel_ref'] == nivel_sel]
    cenarios_ordem = ["Tabela Vigente 01/01/2025", "Tabela Vigente 01/04/2026", "Proposta PL 01/04/2026"]
    cenario_foco = st.sidebar.selectbox("Cenário para Detalhamento", cenarios_ordem)
    
    classe_sel = st.sidebar.selectbox("Classe", sorted(df_nivel['classe'].unique(), reverse=True))
    padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique()))

    st.sidebar.markdown("---")
    func_input = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=0.01)
    saude_input = st.sidebar.number_input("Ressarcimento Saúde (R$)", min_value=0.0, step=0.01)
    
    # Dependentes para IRPF (Dedução de base)
    dep_irpf = st.sidebar.number_input("Nº de Dependentes (para IRPF)", min_value=0, max_value=10, value=0)

    num_filhos, pre_input = 0, 0.0
    if vinculo == "Ativo":
        pontos = st.sidebar.select_slider("Pontos GDAC", [80, 100], 100)
        num_filhos = st.sidebar.number_input("Dependentes (Aux. Pré-escolar)", min_value=0, max_value=5, value=0)
        pre_input = num_filhos * 484.90
    else: pontos = 50

    # --- 5. CÁLCULO ---
    def calcular(nome_cenario):
        try:
            linha = df_nivel[(df_nivel['cenario_ref'] == nome_cenario) & (df_nivel['classe'] == classe_sel) & (df_nivel['padrao'] == padrao_sel)].iloc[0]
            vb = linha['vb']
            gdac = linha['gdac_80'] if pontos == 80 else (linha['gdac_100'] if pontos == 100 else linha['gdac_50'])
            alim = 1175.0 if vinculo == "Ativo" else 0.0
            
            # Base PSS: VB + GDAC + Função
            base_pss = vb + gdac + func_input
            pss_v = calcular_pss(base_pss, vinculo)
            
            # Base IRPF: Somente verbas salariais (Auxílios NÃO entram)
            base_tributavel = vb + gdac + func_input
            ir_v, aliq_v, red_v, base_liq_v = calcular_irpf(base_tributavel, nome_cenario, pss_v, dep_irpf)
            
            bruto_v = vb + gdac + alim + func_input + pre_input + saude_input
            liq_v = bruto_v - ir_v - pss_v
            
            return {"VB": vb, "GDAC": gdac, "ALIM": alim, "FUNC": func_input, "PRE": pre_input, 
                    "SAUDE": saude_input, "BRUTO": bruto_v, "IR": ir_v, "PSS": pss_v, "LIQ": liq_v, 
                    "RED": red_v, "ALIQ": aliq_v, "BASE_CALC": base_liq_v}
        except: return None

    res_25, res_26, res_pl = calcular(cenarios_ordem[0]), calcular(cenarios_ordem[1]), calcular(cenarios_ordem[2])

    # --- 6. INTERFACE ---
    tab1, tab2, tab3 = st.tabs(["🎯 Individual", "⚖️ Comparativo", "📜 Regras"])

    with tab1:
        res = {"Tabela Vigente 01/01/2025": res_25, "Tabela Vigente 01/04/2026": res_26, "Proposta PL 01/04/2026": res_pl}[cenario_foco]
        if res:
            m1, m2, m3 = st.columns(3)
            m1.metric("Bruto Total", f"R$ {formatar_br(res['BRUTO'])}")
            m2.metric("Deduções (IR+PSS)", f"R$ {formatar_br(res['IR'] + res['PSS'])}")
            m3.metric("Líquido Final", f"R$ {formatar_br(res['LIQ'])}")
            
            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Verbas Recebidas:**")
                st.write(f"Vencimento Básico: R$ {formatar_br(res['VB'])}")
                st.write(f"GDAC ({pontos} pts): R$ {formatar_br(res['GDAC'])}")
                st.info(f"Auxílios Isentos (Alim/Pré/Saúde): R$ {formatar_br(res['ALIM']+res['PRE']+res['SAUDE'])}")
            with col_b:
                st.write("**Retenções:**")
                st.write(f"PSS: R$ {formatar_br(res['PSS'])}")
                st.write(f"IRPF: R$ {formatar_br(res['IR'])}")
                st.caption(f"Base de cálculo do IR após deduções: R$ {formatar_br(res['BASE_CALC'])}")

    with tab2:
        if res_25 and res_26 and res_pl:
            tabela = [
                ["TOTAL BRUTO", formatar_br(res_25['BRUTO']), formatar_br(res_26['BRUTO']), formatar_br(res_pl['BRUTO'])],
                ["PSS", f"- {formatar_br(res_25['PSS'])}", f"- {formatar_br(res_26['PSS'])}", f"- {formatar_br(res_pl['PSS'])}"],
                ["IRPF", f"- {formatar_br(res_25['IR'])}", f"- {formatar_br(res_26['IR'])}", f"- {formatar_br(res_pl['IR'])}"],
                ["LÍQUIDO", f"**{formatar_br(res_25['LIQ'])}**", f"**{formatar_br(res_26['LIQ'])}**", f"**{formatar_br(res_pl['LIQ'])}**"]
            ]
            st.table(pd.DataFrame(tabela, columns=["Item", "Jan/25", "Abr/26", "PL Abr/26"]))

    st.markdown("---")
    st.markdown("<div style='text-align: center; color: gray; font-size: 0.8em;'>Simulador MinC - GT de Emendas</div>", unsafe_allow_html=True)
