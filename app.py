import streamlit as st
import pandas as pd
import os

# 1. Configuração da Página e Ícone (Lupa conforme solicitado)
st.set_page_config(page_title="Calculadora Salarial MINC/IPHAN", page_icon="🔍", layout="wide")

# --- FUNÇÕES DE FORMATAÇÃO E LIMPEZA ---

def limpar_valor(valor):
    """Converte valores do CSV (ex: 1.234,56) para float."""
    if isinstance(valor, str):
        v = valor.replace('R$', '').replace('.', '').replace(',', '.').strip()
        try:
            return float(v)
        except ValueError:
            return 0.0
    return float(valor) if valor is not None else 0.0

def formatar_br(valor):
    """Exibe no padrão brasileiro: 7.157,49"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- CÁLCULO DE IRPF (LEI 15.270/2025) ---

def aplicar_reducao_art3a(rendimento, imposto_bruto):
    if rendimento <= 5000.00:
        return min(312.89, imposto_bruto)
    elif 5000.00 < rendimento <= 7350.00:
        reducao = 978.62 - (0.133145 * rendimento)
        return max(0.0, min(reducao, imposto_bruto))
    return 0.0

def calcular_irpf_bruto(base_mensal):
    if base_mensal <= 2259.20: return 0.0, 0.0, 0.0
    elif base_mensal <= 2828.65: return (base_mensal * 0.075) - 169.44, 7.5, 169.44
    elif base_mensal <= 3751.05: return (base_mensal * 0.15) - 381.44, 15.0, 381.44
    elif base_mensal <= 4664.68: return (base_mensal * 0.225) - 662.77, 22.5, 662.77
    else: return (base_mensal * 0.275) - 896.00, 27.5, 896.00

# --- CARREGAMENTO ESPECIAL (DIVISÃO DE TABELAS LADO A LADO) ---

@st.cache_data
def carregar_dados_pl():
    arquivos = {
        "SUPERIOR": "tabela_superior(1).csv",
        "INTERMEDIÁRIO": "tabela_intermediario(1).csv",
        "AUXILIAR": "tabela_auxiliar(1).csv"
    }
    
    dfs_finais = []
    
    for nivel, path in arquivos.items():
        if os.path.exists(path):
            # Lemos o CSV pulando a primeira linha de título
            df_raw = pd.read_csv(path, sep=';', encoding='utf-8-sig', skiprows=1)
            
            # Parte 1: 2025 (Colunas 0 a 10)
            df_25 = df_raw.iloc[:, 0:11].copy()
            df_25.columns = ['classe', 'padrao', 'vb', 'gdac_unit', 'gdac_80', 'gdac_100', 'alim', 'ativo_80', 'ativo_100', 'gdac_50', 'apo_50']
            df_25['vigencia'] = "2025"
            df_25['nivel'] = nivel
            
            # Parte 2: 2026 (Colunas 12 a 22) - Pulamos a coluna 11 que costuma ser vazia
            df_26 = df_raw.iloc[:, 12:23].copy()
            df_26.columns = df_25.columns[:-2] # Copia os mesmos nomes (exceto vigencia e nivel)
            df_26['vigencia'] = "2026"
            df_26['nivel'] = nivel
            
            # Limpeza numérica
            for df in [df_25, df_26]:
                for col in ['vb', 'gdac_80', 'gdac_100', 'alim']:
                    df[col] = df[col].apply(limpar_valor)
                dfs_finais.append(df)
                
    return pd.concat(dfs_finais, ignore_index=True) if dfs_finais else None

df_pl = carregar_dados_pl()

# --- INTERFACE ---

st.title("🔍 Calculadora Salarial MINC/IPHAN")
st.subheader("Simulador de valores com base PL nº 5.874/2025")

if df_pl is None:
    st.error("Erro: Arquivos 'tabela_...(1).csv' não encontrados na pasta.")
    st.stop()

# Sidebar
st.sidebar.header("Dados do Servidor")
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])
ano_base = st.sidebar.radio("Ano de Referência", ["2025", "2026"])

df_nivel = df_pl[df_pl['nivel'] == nivel_sel]
classe_sel = st.sidebar.selectbox("Classe", sorted(df_nivel['classe'].unique(), reverse=True))
padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique()))
pontos_gdac = st.sidebar.select_slider("Pontos GDAC", options=[80, 100], value=80)

valor_funcao = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=100.0)
tem_pre = st.sidebar.checkbox("Auxílio Pré-Escolar (+ R$ 321,00)")

# --- CÁLCULOS ---

try:
    # Busca a linha exata no "banco de dados" fatiado
    row = df_nivel[(df_nivel['classe'] == classe_sel) & 
                   (df_nivel['padrao'] == padrao_sel) & 
                   (df_nivel['vigencia'] == ano_base)].iloc[0]
    
    vb = row['vb']
    gdac = row['gdac_80'] if pontos_gdac == 80 else row['gdac_100']
    alim = row['alim']
    pre = 321.0 if tem_pre else 0.0
    
    bruto = vb + gdac + alim + valor_funcao + pre
    imp_bruto, aliq, _ = calcular_irpf_bruto(bruto)
    reducao = aplicar_reducao_art3a(bruto, imp_bruto) if ano_base == "2026" else 0.0
    ir_final = max(0.0, imp_bruto - reducao)
    liquido = bruto - ir_final

    # Exibição
    m1, m2, m3 = st.columns(3)
    m1.metric("Valor Mensal Bruto", f"R$ {formatar_br(bruto)}")
    m2.metric("IRPF Mensal Final", f"R$ {formatar_br(ir_final)}", 
              delta=f"-R$ {formatar_br(reducao)}" if reducao > 0 else None, delta_color="inverse")
    m3.metric("Valor Mensal Líquido", f"R$ {formatar_br(liquido)}")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.info("**Composição do Rendimento**")
        st.write(f"Vencimento Básico: R$ {formatar_br(vb)}")
        st.write(f"GDAC ({pontos_gdac} pts): R$ {formatar_br(gdac)}")
        st.write(f"Auxílio Alimentação: R$ {formatar_br(alim)}")
        if valor_funcao > 0: st.write(f"Função Comissionada: R$ {formatar_br(valor_funcao)}")
        if tem_pre: st.write(f"Auxílio Pré-Escolar: R$ 321,00")
        st.markdown(f"**Total Bruto: R$ {formatar_br(bruto)}**")
    with c2:
        st.warning("**Detalhamento IRPF**")
        st.write(f"Alíquota: {aliq}%")
        if ano_base == "2026":
            st.success(f"Redução Lei 15.270: R$ {formatar_br(reducao)}")
        st.markdown(f"**Imposto Retido: R$ {formatar_br(ir_final)}**")

except Exception as e:
    st.warning("Selecione os dados na lateral para calcular.")

# --- RODAPÉ ---
st.markdown("---")
st.markdown("<div style='text-align: center; color: #666; font-size: 0.85em;'>Elaboração: GT de Elaboração de Emendas e Comando de Acompanhamento da Negociação</div>", unsafe_allow_html=True)
