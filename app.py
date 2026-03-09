import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO E SUPORTE ---
st.set_page_config(page_title="Simulador Salarial IPHAN", layout="wide", page_icon="🏛️")

def formatar_br(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(valor):
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try: return float(v)
        except: return 0.0
    return float(valor) if valor is not None else 0.0

# --- 2. CÁLCULOS TRIBUTÁRIOS (IRPF 2026 + REDUÇÃO LEI 15.270) ---
def calcular_irpf(base_mensal, cenario_nome):
    if base_mensal <= 2259.20: bruto, aliq = 0.0, 0.0
    elif base_mensal <= 2828.65: bruto, aliq = (base_mensal * 0.075) - 169.44, 7.5
    elif base_mensal <= 3751.05: bruto, aliq = (base_mensal * 0.15) - 381.44, 15.0
    elif base_mensal <= 4664.68: bruto, aliq = (base_mensal * 0.225) - 662.77, 22.5
    else: bruto, aliq = (base_mensal * 0.275) - 896.00, 27.5
    
    reducao = 0.0
    # A redução de base só se aplica aos cenários de 2026 (Vigente e PL)
    if "2026" in cenario_nome or "PL" in cenario_nome:
        if base_mensal <= 5000.00: reducao = min(312.89, bruto)
        elif base_mensal <= 7350.00: reducao = max(0.0, min(978.62 - (0.133145 * base_mensal), bruto))
    
    return max(0.0, bruto - reducao), aliq, reducao

# --- 3. CARREGAMENTO DOS DADOS (INCLUINDO 2025) ---
@st.cache_data
def carregar_dados():
    niveis = {"SUPERIOR": "superior", "INTERMEDIÁRIO": "intermediario", "AUXILIAR": "auxiliar"}
    # Adicionado o sufixo -2025
    sufixos = {"-2025": "Vigente 2025", "-2026": "Vigente 2026", "-PL": "Proposta PL"}
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

# --- 4. BARRA LATERAL ---
st.sidebar.header("⚙️ Parâmetros de Simulação")
vinculo = st.sidebar.radio("Vínculo", ["Ativo", "Aposentado/Pensionista"])
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])

if df_total is not None:
    df_nivel = df_total[df_total['nivel_ref'] == nivel_sel]
    
    # Nova opção de escolha de cenário principal para a Aba 1
    cenario_foco = st.sidebar.selectbox("Cenário para Detalhamento", ["Proposta PL", "Vigente 2026", "Vigente 2025"])
    
    classe_sel = st.sidebar.selectbox("Classe", sorted(df_nivel['classe'].unique(), reverse=True))
    padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique()))

    st.sidebar.markdown("---")
    func = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=0.01, format="%.2f")
    saude = st.sidebar.number_input("Ressarcimento Saúde (R$)", min_value=0.0, step=0.01, format="%.2f")

    pre = 0.0
    if vinculo == "Ativo":
        pontos = st.sidebar.select_slider("Pontos GDAC", [80, 100], 100)
        if st.sidebar.checkbox("Auxílio Pré-Escolar (+321,00)"): pre = 321.0
    else:
        pontos = 50

    # --- 5. PROCESSAMENTO DOS TRÊS CENÁRIOS ---
    def calcular(nome_cenario):
        try:
            linha = df_nivel[(df_nivel['cenario_ref'] == nome_cenario) & 
                             (df_nivel['classe'] == classe_sel) & 
                             (df_nivel['padrao'] == padrao_sel)].iloc[0]
            vb = linha['vb']
            gdac = linha['gdac_80'] if pontos == 80 else (linha['gdac_100'] if pontos == 100 else linha['gdac_50'])
            alim = 1175.0 if vinculo == "Ativo" else 0.0
            
            base_irpf = vb + gdac + func
            ir, aliq, red = calcular_irpf(base_irpf, nome_cenario)
            bruto = vb + gdac + alim + func + pre + saude
            
            return {"VB": vb, "GDAC": gdac, "ALIM": alim, "FUNC": func, "PRE": pre, 
                    "SAUDE": saude, "BRUTO": bruto, "IR": ir, "LIQ": bruto - ir, "RED": red, "ALIQ": aliq}
        except: return None

    res_25 = calcular("Vigente 2025")
    res_26 = calcular("Vigente 2026")
    res_pl = calcular("Proposta PL")

    # --- 6. INTERFACE PRINCIPAL ---
    st.title("📊 Simulador Salarial IPHAN")

    tab1, tab2 = st.tabs(["🎯 Calculadora Individual", "⚖️ Quadro Comparativo (Triplo)"])

    with tab1:
        res = {"Proposta PL": res_pl, "Vigente 2026": res_26, "Vigente 2025": res_25}[cenario_foco]
        
        if res:
            st.subheader(f"Cenário: {cenario_foco}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Bruto", f"R$ {formatar_br(res['BRUTO'])}")
            c2.metric("IRPF", f"R$ {formatar_br(res['IR'])}")
            c3.metric("Líquido", f"R$ {formatar_br(res['LIQ'])}")
            
            st.markdown("---")
            st.write(f"**Detalhamento ({nivel_sel} - {classe_sel}/{padrao_sel}):**")
            st.info(f"Vencimento Básico: R$ {formatar_br(res['VB'])}  |  GDAC ({pontos} pts): R$ {formatar_br(res['GDAC'])}")
        else:
            st.error("Dados deste cenário não encontrados.")

    with tab2:
        st.subheader("Linha do Tempo: Evolução Salarial")
        if res_25 and res_26 and res_pl:
            dados_comp = [
                ["Vencimento Básico", formatar_br(res_25['VB']), formatar_br(res_26['VB']), formatar_br(res_pl['VB'])],
                ["GDAC", formatar_br(res_25['GDAC']), formatar_br(res_26['GDAC']), formatar_br(res_pl['GDAC'])],
                ["Total Bruto", formatar_br(res_25['BRUTO']), formatar_br(res_26['BRUTO']), formatar_br(res_pl['BRUTO'])],
                ["Líquido Final", f"**{formatar_br(res_25['LIQ'])}**", f"**{formatar_br(res_26['LIQ'])}**", f"**{formatar_br(res_pl['LIQ'])}**"]
            ]
            df_comp = pd.DataFrame(dados_comp, columns=["Rubrica", "Jan/2025", "Abr/2026 (Vigente)", "Proposta PL"])
            st.table(df_comp)
            
            ganho_total = res_pl['LIQ'] - res_25['LIQ']
            st.success(f"📈 O ganho acumulado entre HOJE e a PROPOSTA do PL é de **R$ {formatar_br(ganho_total)}** no líquido.")
