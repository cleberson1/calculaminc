import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO E SUPORTE ---
st.set_page_config(page_title="Simulador Salarial MINC", layout="wide", page_icon="🏛️")

def formatar_br(valor):
    """Formata valores para o padrão R$ 1.234,56"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(valor):
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try: return float(v)
        except: return 0.0
    return float(valor) if valor is not None else 0.0

# --- 2. MOTOR DE CÁLCULO ---

def calcular_pss(base_contribuicao, vinculo):
    """Calcula PSS progressivo (Portaria nº 6/2025)"""
    teto_rgps = 8157.41
    base_calculo = base_contribuicao if vinculo == "Ativo" else max(0, base_contribuicao - teto_rgps)
    
    faixas = [
        (1518.00, 0.075), (2793.88, 0.09), (4190.83, 0.12),
        (8157.41, 0.14), (13969.49, 0.145), (27938.95, 0.165),
        (54480.97, 0.19), (float('inf'), 0.22)
    ]
    
    total_pss, limite_anterior = 0.0, 0.0
    for limite, aliquota in faixas:
        if base_calculo > limite_anterior:
            base_na_faixa = min(base_calculo, limite) - limite_anterior
            total_pss += base_na_faixa * aliquota
            limite_anterior = limite
    return total_pss

def calcular_irpf(base_mensal, cenario_nome):
    """Tabela IRPF com as reduções da Lei 15.270 e Lei 15.367"""
    if base_mensal <= 2259.20: bruto, aliq = 0.0, 0.0
    elif base_mensal <= 2828.65: bruto, aliq = (base_mensal * 0.075) - 169.44, 7.5
    elif base_mensal <= 3751.05: bruto, aliq = (base_mensal * 0.15) - 381.44, 15.0
    elif base_mensal <= 4664.68: bruto, aliq = (base_mensal * 0.225) - 662.77, 22.5
    else: bruto, aliq = (base_mensal * 0.275) - 896.00, 27.5
    
    reducao = 0.0
    if "15.367" in cenario_nome:
        if base_mensal <= 5000.00: reducao = min(312.89, bruto)
        elif base_mensal <= 7350.00: reducao = max(0.0, min(978.62 - (0.133145 * base_mensal), bruto))
    return max(0.0, bruto - reducao), aliq, reducao

# --- 3. CARREGAMENTO DE DADOS (UTF-8) ---

@st.cache_data
def carregar_tabela_saude():
    if os.path.exists("assistencia_saude_complementar.csv"):
        # Já que você converteu para UTF-8, usamos utf-8 direto
        return pd.read_csv("assistencia_saude_complementar.csv", sep=';', encoding='utf-8')
    return None

def obter_valor_saude(base_calculo, faixa_etaria_col, df_saude):
    if df_saude is None or not faixa_etaria_col: return 0.0
    # Lógica de faixas de renda baseada no CSV
    if base_calculo <= 3000: idx = 0
    elif base_calculo <= 6000: idx = 1
    elif base_calculo <= 9000: idx = 2
    elif base_calculo <= 12000: idx = 3
    elif base_calculo <= 15000: idx = 4
    elif base_calculo <= 18000: idx = 5
    elif base_calculo <= 21000: idx = 6
    else: idx = 7
    return limpar_valor(df_saude.iloc[idx][faixa_etaria_col])

@st.cache_data
def carregar_dados():
    niveis = {"SUPERIOR": "superior", "INTERMEDIÁRIO": "intermediario", "AUXILIAR": "auxiliar"}
    sufixos = {"-2025": "Tabela Vigente 01/01/2025", "-PL": "Lei nº 15.367/2026"}
    dfs = []
    for nome_n, prefixo in niveis.items():
        for suf, cenario in sufixos.items():
            path = f"tabela_{prefixo}{suf}.csv"
            if os.path.exists(path):
                df = pd.read_csv(path, sep=';', encoding='utf-8')
                df['nivel_ref'], df['cenario_ref'] = nome_n, cenario
                for col in ['vb', 'gdac_80', 'gdac_100', 'gdac_50']:
                    if col in df.columns: df[col] = df[col].apply(limpar_valor)
                dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else None

df_total = carregar_dados()
df_saude_ref = carregar_tabela_saude()

# --- 4. INTERFACE LATERAL ---
st.sidebar.header("⚙️ Parâmetros")
vinculo = st.sidebar.radio("Situação", ["Ativo", "Aposentado/Pensionista"])
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])

if df_total is not None:
    df_nivel = df_total[df_total['nivel_ref'] == nivel_sel]
    cenario_foco = st.sidebar.selectbox("Cenário para Detalhamento", ["Tabela Vigente 01/01/2025", "Lei nº 15.367/2026"])
    
    classe_sel = st.sidebar.selectbox("Classe", sorted(df_nivel['classe'].unique(), reverse=True))
    padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique()))

    st.sidebar.markdown("---")
    # Seleção de Saúde Suplementar
    faixa_etaria_sel = None
    if df_saude_ref is not None:
        faixa_etaria_sel = st.sidebar.selectbox("Sua Faixa Etária (Saúde)", df_saude_ref.columns[1:])
    
    func_input = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=0.01)
    dep_ir = st.sidebar.number_input("Dependentes IRPF", min_value=0, max_value=10)

    if vinculo == "Ativo":
        pontos = st.sidebar.select_slider("Pontos GDAC", [50, 80, 100], 100)
        pre_input = st.sidebar.number_input("Filhos (Pré-Escolar)", 0, 5) * 484.90
        alim = 1175.0
    else:
        pontos, pre_input, alim = 50, 0.0, 0.0

    # --- 5. LÓGICA DE CÁLCULO ---
    def calcular(nome_cenario):
        try:
            filt = (df_total['cenario_ref'] == nome_cenario) & (df_total['nivel_ref'] == nivel_sel) & \
                   (df_total['classe'] == classe_sel) & (df_total['padrao'] == padrao_sel)
            linha = df_total[filt].iloc[0]
            
            vb = linha['vb']
            gdac = linha[f'gdac_{pontos}']
            saude = obter_valor_saude(vb + gdac, faixa_etaria_sel, df_saude_ref)
            
            base_pss = vb + gdac + func_input
            pss = calcular_pss(base_pss, vinculo)
            
            base_irpf = max(0, (vb + gdac + func_input) - pss - (dep_ir * 189.59))
            ir, aliq, red = calcular_irpf(base_irpf, nome_cenario)
            
            bruto = vb + gdac + alim + func_input + pre_input + saude
            return {"VB": vb, "GDAC": gdac, "ALIM": alim, "FUNC": func_input, "PRE": pre_input, 
                    "SAUDE": saude, "BRUTO": bruto, "IR": ir, "PSS": pss, "LIQ": bruto-ir-pss, "RED": red}
        except: return None

    res_25 = calcular("Tabela Vigente 01/01/2025")
    res_26 = calcular("Lei nº 15.367/2026")

    # --- 6. UI PRINCIPAL ---
    st.title("🗿 Simulador Salarial MINC")
    t1, t2, t3 = st.tabs(["🎯 Individual", "📊 Comparativo", "📜 Normas"])

    with t1:
        res = res_25 if cenario_foco == "Tabela Vigente 01/01/2025" else res_26
        if res:
            c1, c2, c3 = st.columns(3)
            c1.metric("Bruto", f"R$ {formatar_br(res['BRUTO'])}")
            c2.metric("Descontos", f"R$ {formatar_br(res['IR'] + res['PSS'])}")
            c3.metric("Líquido", f"R$ {formatar_br(res['LIQ'])}")
            
            col_l, col_r = st.columns(2)
            with col_l:
                st.write("**Remuneração:**")
                st.write(f"Vencimento Básico: R$ {formatar_br(res['VB'])}")
                st.write(f"GDAC ({pontos} pts): R$ {formatar_br(res['GDAC'])}")
                if res['SAUDE'] > 0: st.success(f"Saúde Suplementar: R$ {formatar_br(res['SAUDE'])}")
            with col_r:
                st.write("**Deduções:**")
                st.write(f"Previdência (PSS): R$ {formatar_br(res['PSS'])}")
                st.write(f"Imposto de Renda: R$ {formatar_br(res['IR'])}")
                if res['RED'] > 0: st.info(f"Redução Lei 15.270/25: R$ {formatar_br(res['RED'])}")

    with t2:
        if res_25 and res_26:
            st.subheader("Evolução Salarial")
            dados_comp = {
                "Item": ["Vencimento Básico", "GDAC", "Auxílios/Saúde", "TOTAL BRUTO", "PSS", "IRPF", "LÍQUIDO"],
                "Atual (2025)": [formatar_br(res_25['VB']), formatar_br(res_25['GDAC']), formatar_br(res_25['ALIM']+res_25['SAUDE']), formatar_br(res_25['BRUTO']), f"-{formatar_br(res_25['PSS'])}", f"-{formatar_br(res_25['IR'])}", f"**{formatar_br(res_25['LIQ'])}**"],
                "Lei 15.367/26": [formatar_br(res_26['VB']), formatar_br(res_26['GDAC']), formatar_br(res_26['ALIM']+res_26['SAUDE']), formatar_br(res_26['BRUTO']), f"-{formatar_br(res_26['PSS'])}", f"-{formatar_br(res_26['IR'])}", f"**{formatar_br(res_26['LIQ'])}**"]
            }
            st.table(pd.DataFrame(dados_comp))
            ganho = res_26['LIQ'] - res_25['LIQ']
            st.success(f"📈 Diferença Líquida: R$ {formatar_br(ganho)} ({(ganho/res_25['LIQ'])*100:.2f}%)")

    with t3:
        st.write("Cálculos baseados na **Lei nº 15.367/2026** e Portarias vigentes de saúde e previdência.")
