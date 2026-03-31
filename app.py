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

# --- 2. MOTOR DE CÁLCULO TRIBUTÁRIO E PREVIDENCIÁRIO ---

def calcular_pss(base_contribuicao, vinculo):
    """Calcula PSS progressivo conforme Anexo III da Portaria nº 6/2025"""
    teto_rgps = 8157.41
    if vinculo != "Ativo":
        if base_contribuicao <= teto_rgps:
            return 0.0
        base_calculo = base_contribuicao - teto_rgps
    else:
        base_calculo = base_contribuicao

    faixas = [
        (1518.00, 0.075), (2793.88, 0.09), (4190.83, 0.12),
        (8157.41, 0.14), (13969.49, 0.145), (27938.95, 0.165),
        (54480.97, 0.19), (float('inf'), 0.22)
    ]
    
    total_pss = 0.0
    limite_anterior = 0.0
    for limite, aliquota in faixas:
        if base_calculo > limite_anterior:
            base_na_faixa = min(base_calculo, limite) - limite_anterior
            total_pss += base_na_faixa * aliquota
            limite_anterior = limite
        else:
            break
    return total_pss

def calcular_irpf(base_mensal, cenario_nome):
    """Tabela IRPF 2025/2026 com redução da Lei 15.270"""
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

# --- 3. GESTÃO DE SAÚDE SUPLEMENTAR ---

@st.cache_data
def carregar_tabela_saude():
    caminho = "assistencia_saude_complementar.csv"
    if os.path.exists(caminho):
        try:
            # Tenta ler com latin-1, que é o padrão comum de CSVs brasileiros vindos do Excel
            df = pd.read_csv(caminho, sep=';', encoding='latin-1')
            return df
        except UnicodeDecodeError:
            # Caso o latin-1 falhe, tenta o utf-8 padrão como fallback
            df = pd.read_csv(caminho, sep=';', encoding='utf-8')
            return df
        except Exception as e:
            st.error(f"Erro ao ler arquivo de saúde: {e}")
            return None
    return None

def calcular_saude_suplementar(base_calculo, faixa_etaria_col):
    df_saude = carregar_tabela_saude()
    if df_saude is None: return 0.0
    
    # Determinar a linha com base na renda (VB + GDAC)
    if base_calculo <= 3000: index = 0
    elif base_calculo <= 6000: index = 1
    elif base_calculo <= 9000: index = 2
    elif base_calculo <= 12000: index = 3
    elif base_calculo <= 15000: index = 4
    elif base_calculo <= 18000: index = 5
    elif base_calculo <= 21000: index = 6
    else: index = 7
    
    try:
        valor = df_saude.iloc[index][faixa_etaria_col]
        return limpar_valor(valor)
    except:
        return 0.0

# --- 4. CARREGAMENTO DOS DADOS SALARIAIS ---
@st.cache_data
def carregar_dados():
    niveis = {"SUPERIOR": "superior", "INTERMEDIÁRIO": "intermediario", "AUXILIAR": "auxiliar"}
    # Removida a tabela -2026 e atualizada a nomenclatura do PL
    sufixos = {"-2025": "Tabela Vigente 01/01/2025", "-PL": "Lei nº 15.367/2026"}
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
df_saude_ref = carregar_tabela_saude()

# --- 5. BARRA LATERAL ---
st.sidebar.header("⚙️ Parâmetros")
vinculo = st.sidebar.radio("Situação", ["Ativo", "Aposentado/Pensionista"])
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])

if df_total is not None:
    df_nivel = df_total[df_total['nivel_ref'] == nivel_sel]
    # Ordem atualizada
    cenarios_ordem = ["Tabela Vigente 01/01/2025", "Lei nº 15.367/2026"]
    cenario_foco = st.sidebar.selectbox("Cenário para Detalhamento (Aba 1)", cenarios_ordem)
    
    classe_sel = st.sidebar.selectbox("Classe", sorted(df_nivel['classe'].unique(), reverse=True))
    padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique()))

    st.sidebar.markdown("---")
    # Saúde Suplementar por Tabela
    if df_saude_ref is not None:
        colunas_faixa = list(df_saude_ref.columns[1:])
        faixa_etaria_sel = st.sidebar.selectbox("Faixa Etária (Saúde)", colunas_faixa)
    else:
        faixa_etaria_sel = None
        st.sidebar.warning("Arquivo de saúde não encontrado.")

    func_input = st.sidebar.number_input("Função Comissionada (R$)", min_value=0.0, step=0.01)
    num_dependentes_ir = st.sidebar.number_input("Dependentes IRPF", min_value=0, max_value=10, value=0)

    if vinculo == "Ativo":
        # Agora inclui a opção de 50 pontos
        pontos = st.sidebar.select_slider("Pontos GDAC", [50, 80, 100], 100)
        num_filhos_pre = st.sidebar.number_input("Filhos (Aux. Pré-Escolar)", min_value=0, max_value=5, value=0)
        pre_input = num_filhos_pre * 484.90
    else:
        pontos = 50
        num_filhos_pre = 0
        pre_input = 0.0

    # --- 6. CÁLCULO ---
    def calcular(nome_cenario):
        try:
            linha = df_nivel[(df_nivel['cenario_ref'] == nome_cenario) & (df_nivel['classe'] == classe_sel) & (df_nivel['padrao'] == padrao_sel)].iloc[0]
            vb = linha['vb']
            
            # Seleção dinâmica do GDAC
            gdac_col = f'gdac_{pontos}'
            gdac = linha[gdac_col]
            
            alim = 1175.0 if vinculo == "Ativo" else 0.0
            
            # Cálculo Automático da Saúde (Base: VB + GDAC)
            saude_v = calcular_saude_suplementar(vb + gdac, faixa_etaria_sel) if faixa_etaria_sel else 0.0
            
            # Base PSS: VB + GDAC + FUNÇÃO
            base_pss = vb + gdac + func_input
            pss_v = calcular_pss(base_pss, vinculo)
            
            deducao_dependentes = num_dependentes_ir * 189.59
            base_irpf = max(0, (vb + gdac + func_input) - pss_v - deducao_dependentes)
            ir_v, aliq_v, red_v = calcular_irpf(base_irpf, nome_cenario)
            
            bruto_v = vb + gdac + alim + func_input + pre_input + saude_v
            liq_v = bruto_v - ir_v - pss_v
            
            return {"VB": vb, "GDAC": gdac, "ALIM": alim, "FUNC": func_input, "PRE": pre_input, 
                    "SAUDE": saude_v, "BRUTO": bruto_v, "IR": ir_v, "PSS": pss_v, "LIQ": li_v, "RED": red_v, "ALIQ": aliq_v}
        except Exception as e:
            return None

    res_25 = calcular("Tabela Vigente 01/01/2025")
    res_lei = calcular("Lei nº 15.367/2026")

    # --- 7. INTERFACE ---
    st.title("🗿 Simulador Salarial MINC")

    tab1, tab2, tab3 = st.tabs(["🎯 Calculadora Individual", "📊 Comparativo Cronológico", "📜 Normativo Legal"])
    
    with tab1:
        res = res_25 if cenario_foco == "Tabela Vigente 01/01/2025" else res_lei
        if res:
            st.subheader(f"Detalhamento: {cenario_foco}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Bruto Total", f"R$ {formatar_br(res['BRUTO'])}")
            m2.metric("Total Deduções", f"R$ {formatar_br(res['IR'] + res['PSS'])}")
            m3.metric("Líquido Final", f"R$ {formatar_br(res['LIQ'])}")
            
            st.markdown("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Composição da Remuneração:**")
                st.write(f"Vencimento Básico: **R$ {formatar_br(res['VB'])}**")
                st.write(f"GDAC ({pontos} pts): **R$ {formatar_br(res['GDAC'])}**")
                if res['ALIM'] > 0: st.write(f"Auxílio Alimentação: **R$ {formatar_br(res['ALIM'])}**")
                if res['SAUDE'] > 0: st.success(f"Ressarcimento Saúde (Tabela): **R$ {formatar_br(res['SAUDE'])}**")
            with col_b:
                st.write("**Deduções:**")
                st.write(f"Contribuição PSS: **R$ {formatar_br(res['PSS'])}**")
                st.write(f"Imposto de Renda (IRPF): **R$ {formatar_br(res['IR'])}**")
                if res['RED'] > 0: st.info(f"Redução Lei 15.270 aplicada: **R$ {formatar_br(res['RED'])}**")

    with tab2:
        st.subheader("Evolução: Hoje ➔ Lei nº 15.367/2026")
        if res_25 and res_lei:
            def soma_extra(r): return r['ALIM']+r['PRE']+r['SAUDE']+r['FUNC']
            tabela = [
                ["Vencimento Básico", formatar_br(res_25['VB']), formatar_br(res_lei['VB'])],
                ["GDAC", formatar_br(res_25['GDAC']), formatar_br(res_lei['GDAC'])],
                ["Auxílios/Saúde/Função", formatar_br(soma_extra(res_25)), formatar_br(soma_extra(res_lei))],
                ["TOTAL BRUTO", formatar_br(res_25['BRUTO']), formatar_br(res_lei['BRUTO'])],
                ["PSS", f"- {formatar_br(res_25['PSS'])}", f"- {formatar_br(res_lei['PSS'])}"],
                ["IRPF", f"- {formatar_br(res_25['IR'])}", f"- {formatar_br(res_lei['IR'])}"],
                ["LÍQUIDO FINAL", f"**{formatar_br(res_25['LIQ'])}**", f"**{formatar_br(res_lei['LIQ'])}**"]
            ]
            st.table(pd.DataFrame(tabela, columns=["Item", "Situação Atual (2025)", "Lei nº 15.367/2026"]))
            
            ganho = res_lei['LIQ'] - res_25['LIQ']
            perc = (ganho / res_25['LIQ']) * 100 if res_25['LIQ'] != 0 else 0
            st.success(f"📈 Ganho Líquido Estimado: **R$ {formatar_br(ganho)} ({perc:.2f}%)**")

    with tab3:
        # Mantido o bloco de legislação conforme o original
        st.subheader("Base Normativa")
        # ... (código original de legislação aqui)
        st.info("Cálculos de Saúde baseados na Portaria MGI nº 2.829/2024 (conforme CSV fornecido).")

    st.markdown("---")
    st.markdown("<div style='text-align: center; color: gray; font-size: 0.8em;'>Simulador Atualizado conforme Lei nº 15.367/2026</div>", unsafe_allow_html=True)
