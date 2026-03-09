import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO E SUPORTE ---
st.set_page_config(page_title="Simulador Salarial IPHAN", layout="wide", page_icon="🏛️")

def formatar_br(valor):
    """Formata valores para o padrão R$ 1.234,56"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(valor):
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try: return float(v)
        except: return 0.0
    return float(valor) if valor is not None else 0.0

# --- 2. CÁLCULOS TRIBUTÁRIOS ---

def calcular_irpf(base_mensal, cenario_nome):
    if base_mensal <= 2259.20: bruto, aliq = 0.0, 0.0
    elif base_mensal <= 2828.65: bruto, aliq = (base_mensal * 0.075) - 169.44, 7.5
    elif base_mensal <= 3751.05: bruto, aliq = (base_mensal * 0.15) - 381.44, 15.0
    elif base_mensal <= 4664.68: bruto, aliq = (base_mensal * 0.225) - 662.77, 22.5
    else: bruto, aliq = (base_mensal * 0.275) - 896.00, 27.5
    
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

# --- 4. BARRA LATERAL ---

st.sidebar.header("⚙️ Parâmetros")
vinculo = st.sidebar.radio("Vínculo", ["Ativo", "Aposentado/Pensionista"])
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])

# Garantir que temos dados antes de prosseguir
if df_total is not None:
    df_nivel = df_total[df_total['nivel_ref'] == nivel_sel]
    classes_disp = sorted(df_nivel['classe'].unique(), reverse=True)
    classe_sel = st.sidebar.selectbox("Classe", classes_disp)
    
    padroes_disp = sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique())
    padrao_sel = st.sidebar.selectbox("Padrão", padroes_disp)

    st.sidebar.markdown("---")
    func = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=0.01, format="%.2f")
    saude = st.sidebar.number_input("Ressarcimento Saúde (R$)", min_value=0.0, step=0.01, format="%.2f")

    pre = 0.0
    if vinculo == "Ativo":
        pontos = st.sidebar.select_slider("Pontos GDAC", [80, 100], 100)
        if st.sidebar.checkbox("Auxílio Pré-Escolar (+321,00)"): pre = 321.0
    else:
        pontos = 50

    # --- 5. PROCESSAMENTO CENTRALIZADO ---
    def calcular_por_cenario(nome_cenario):
        try:
            # Aqui estava o erro: garantindo que filtramos o df_nivel corretamente
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
        except:
            return None

    res_vig = calcular_por_cenario("Vigente 2026")
    res_pl = calcular_por_cenario("Proposta PL")

    # --- 6. EXIBIÇÃO ---
    st.title("📊 Simulador Salarial MINC/IPHAN")

    if res_vig and res_pl:
        tab1, tab2 = st.tabs(["🎯 Calculadora Individual", "⚖️ Quadro Comparativo"])

        with tab1:
            st.subheader(f"Detalhamento: {nivel_sel} - {classe_sel}/{padrao_sel}")
            escolha = st.radio("Cenário:", ["Proposta PL", "Vigente 2026"], horizontal=True)
            res = res_pl if escolha == "Proposta PL" else res_vig
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Bruto Total", f"R$ {formatar_br(res['BRUTO'])}")
            c2.metric("IRPF", f"R$ {formatar_br(res['IR'])}", delta=f"-R$ {formatar_br(res['RED'])}" if res['RED']>0 else None, delta_color="inverse")
            c3.metric("Líquido", f"R$ {formatar_br(res['LIQ'])}")

            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Rubricas de Recebimento:**")
                st.write(f"Vencimento Básico: R$ {formatar_br(res['VB'])}")
                st.write(f"GDAC ({pontos} pts): R$ {formatar_br(res['GDAC'])}")
                if res['ALIM'] > 0: st.write(f"Auxílio Alimentação: R$ {formatar_br(res['ALIM'])}")
                if res['PRE'] > 0: st.success(f"Auxílio Pré-Escolar: R$ {formatar_br(res['PRE'])}")
            with col_b:
                st.write("**Descontos e Impostos:**")
                st.write(f"Alíquota: {res['ALIQ']}%")
                if res['RED'] > 0: st.info(f"Redução Lei 15.270: R$ {formatar_br(res['RED'])}")

        with tab2:
            st.subheader("Comparativo PL vs Vigente")
            dados_tab = [
                ["Vencimento Básico", formatar_br(res_vig['VB']), formatar_br(res_pl['VB'])],
                ["GDAC", formatar_br(res_vig['GDAC']), formatar_br(res_pl['GDAC'])],
                ["Auxílios/Função/Saúde", formatar_br(res_vig['ALIM']+res_vig['PRE']+res_vig['FUNC']+res_vig['SAUDE']), 
                                         formatar_br(res_pl['ALIM']+res_pl['PRE']+res_pl['FUNC']+res_pl['SAUDE'])],
                ["TOTAL BRUTO", f"**{formatar_br(res_vig['BRUTO'])}**", f"**{formatar_br(res_pl['BRUTO'])}**"],
                ["LÍQUIDO FINAL", f"**{formatar_br(res_vig['LIQ'])}**", f"**{formatar_br(res_pl['LIQ'])}**"]
            ]
            st.table(pd.DataFrame(dados_tab, columns=["Descrição", "Vigente 2026", "Proposta PL"]))
            st.success(f"Ganho real no bolso: R$ {formatar_br(res_pl['LIQ'] - res_vig['LIQ'])} mensais.")

else:
    st.error("Erro: Arquivos CSV não encontrados no diretório.")
