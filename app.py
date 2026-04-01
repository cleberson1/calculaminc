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
        try: 
            return float(v)
        except: 
            return 0.0
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
    if base_mensal <= 2259.20: 
        bruto, aliq = 0.0, 0.0
    elif base_mensal <= 2828.65: 
        bruto, aliq = (base_mensal * 0.075) - 169.44, 7.5
    elif base_mensal <= 3751.05: 
        bruto, aliq = (base_mensal * 0.15) - 381.44, 15.0
    elif base_mensal <= 4664.68: 
        bruto, aliq = (base_mensal * 0.225) - 662.77, 22.5
    else: 
        bruto, aliq = (base_mensal * 0.275) - 896.00, 27.5
    
    reducao = 0.0
    if "15.367" in cenario_nome:
        if base_mensal <= 5000.00: 
            reducao = min(312.89, bruto)
        elif base_mensal <= 7350.00: 
            reducao = max(0.0, min(978.62 - (0.133145 * base_mensal), bruto))
    return max(0.0, bruto - reducao), aliq, reducao

# --- 3. CARREGAMENTO DE DADOS (UTF-8) ---

@st.cache_data
def carregar_tabela_saude():
    try:
        if os.path.exists("assistencia_saude_complementar.csv"):
            return pd.read_csv("assistencia_saude_complementar.csv", sep=';', encoding='utf-8')
        return None
    except Exception as e:
        st.warning(f"Erro ao carregar arquivo de saúde: {e}")
        return None

def obter_valor_saude(base_calculo, faixa_etaria_col, df_saude):
    if df_saude is None or not faixa_etaria_col: 
        return 0.0
    try:
        if base_calculo <= 3000: 
            idx = 0
        elif base_calculo <= 6000: 
            idx = 1
        elif base_calculo <= 9000: 
            idx = 2
        elif base_calculo <= 12000: 
            idx = 3
        elif base_calculo <= 15000: 
            idx = 4
        elif base_calculo <= 18000: 
            idx = 5
        elif base_calculo <= 21000: 
            idx = 6
        else: 
            idx = 7
        return limpar_valor(df_saude.iloc[idx][faixa_etaria_col])
    except Exception as e:
        return 0.0

@st.cache_data
def carregar_tabela_fce():
    try:
        if not os.path.exists("fce.csv"):
            return None
        
        # Tenta diferentes codificações
        codificacoes = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        for encoding in codificacoes:
            try:
                df = pd.read_csv("fce.csv", sep=';', encoding=encoding)
                if 'Função' in df.columns and 'Valor' in df.columns:
                    return df
            except:
                continue
        
        st.warning("Não foi possível ler o arquivo fce.csv com as codificações disponíveis")
        return None
    except Exception as e:
        st.warning(f"Erro ao carregar arquivo fce.csv: {e}")
        return None

@st.cache_data
def carregar_dados():
    try:
        niveis = {"SUPERIOR": "superior", "INTERMEDIÁRIO": "intermediario", "AUXILIAR": "auxiliar"}
        sufixos = {"-2025": "Tabela Vigente 01/01/2025", "-PL": "Lei nº 15.367/2026"}
        dfs = []
        
        for nome_n, prefixo in niveis.items():
            for suf, cenario in sufixos.items():
                path = f"tabela_{prefixo}{suf}.csv"
                if os.path.exists(path):
                    try:
                        df = pd.read_csv(path, sep=';', encoding='utf-8')
                        df['nivel_ref'], df['cenario_ref'] = nome_n, cenario
                        for col in ['vb', 'gdac_80', 'gdac_100', 'gdac_50']:
                            if col in df.columns: 
                                df[col] = df[col].apply(limpar_valor)
                        dfs.append(df)
                    except Exception as e:
                        st.warning(f"Erro ao carregar {path}: {e}")
        
        return pd.concat(dfs, ignore_index=True) if dfs else None
    except Exception as e:
        st.error(f"Erro ao carregar dados das tabelas: {e}")
        return None

# --- 4. CARREGAMENTO DOS DADOS ---
df_total = carregar_dados()
df_saude_ref = carregar_tabela_saude()
df_fce_ref = carregar_tabela_fce()

# --- 5. INTERFACE LATERAL ---
st.sidebar.header("⚙️ Parâmetros")

# Verifica se os dados foram carregados
if df_total is None:
    st.error("""
    ❌ **Erro: Dados não carregados!**
    
    O sistema não conseguiu carregar as tabelas necessárias. Verifique se:
    1. Os arquivos CSV estão no diretório correto
    2. Os arquivos têm os nomes esperados:
       - tabela_superior-2025.csv
       - tabela_superior-PL.csv
       - tabela_intermediario-2025.csv
       - tabela_intermediario-PL.csv
       - tabela_auxiliar-2025.csv
       - tabela_auxiliar-PL.csv
    3. Os arquivos estão no formato UTF-8
    """)
    st.stop()

# Widgets principais
vinculo = st.sidebar.radio("Situação", ["Ativo", "Aposentado/Pensionista"])
nivel_sel = st.sidebar.selectbox("Nível", ["SUPERIOR", "INTERMEDIÁRIO", "AUXILIAR"])

df_nivel = df_total[df_total['nivel_ref'] == nivel_sel]
cenario_foco = st.sidebar.selectbox("Cenário para Detalhamento", ["Tabela Vigente 01/01/2025", "Lei nº 15.367/2026"])

classe_sel = st.sidebar.selectbox("Classe", sorted(df_nivel['classe'].unique(), reverse=True))
padrao_sel = st.sidebar.selectbox("Padrão", sorted(df_nivel[df_nivel['classe'] == classe_sel]['padrao'].unique()))

st.sidebar.markdown("---")

# Botão para saúde
usar_saude = st.sidebar.toggle("Recebe Saúde Suplementar?", value=False)
faixa_etaria_sel = None
if usar_saude and df_saude_ref is not None:
    faixa_etaria_sel = st.sidebar.selectbox("Sua Faixa Etária (Saúde)", df_saude_ref.columns[1:])
elif usar_saude:
    st.sidebar.warning("Arquivo de saúde não encontrado.")

st.sidebar.markdown("---")

# Botão para função comissionada
usar_fce = st.sidebar.toggle("Exerce função comissionada?", value=False)

func_input = 0.0

if usar_fce:
    col_info, col_help = st.sidebar.columns([0.85, 0.15])
    with col_help:
        st.help("""**Explicando as funções comissionadas:**
Código 1: Cargos de direção;
Código 2: Cargos de acessoramento;
Código 3: Cargos de direção de projetos;
Código 4: Acessoramento técnico especializado.

Considerando que todas as remunerações de Funções Comissionadas estão reguladas pelos seguintes regramentos jurídicos: Lei nº 11.356/2006, Lei nº 11.526/2007, Lei nº 14.204/2021 e Lei nº 15.141/2025""")
    
    with col_info:
        if df_fce_ref is not None:
            fce_selecionada = st.selectbox("Selecione sua Função", df_fce_ref['Função'].unique())
            valor_fce_str = df_fce_ref[df_fce_ref['Função'] == fce_selecionada]['Valor'].values[0]
            func_input = limpar_valor(valor_fce_str)
            st.caption(f"Valor da Função: R$ {formatar_br(func_input)}")
        else:
            st.error("Arquivo fce.csv não encontrado. Função comissionada indisponível.")

# Campo de dependentes
dep_ir = st.sidebar.number_input("Dependentes IRPF", min_value=0, max_value=10, value=0)

# Configurações específicas por vínculo
if vinculo == "Ativo":
    pontos = st.sidebar.select_slider("Pontos GDAC", [50, 80, 100], 100)
    pre_input = st.sidebar.number_input("Filhos (Pré-Escolar)", min_value=0, max_value=5, value=0) * 484.90
    alim = 1175.0
else:
    pontos = 50
    pre_input = 0.0
    alim = 0.0

# --- 6. LÓGICA DE CÁLCULO ---
def calcular(nome_cenario):
    try:
        filt = (df_total['cenario_ref'] == nome_cenario) & (df_total['nivel_ref'] == nivel_sel) & \
               (df_total['classe'] == classe_sel) & (df_total['padrao'] == padrao_sel)
        linha = df_total[filt].iloc[0]
        
        vb = linha['vb']
        gdac = linha[f'gdac_{pontos}']
        
        # Saúde calculada apenas se o botão estiver ativo
        saude = obter_valor_saude(vb + gdac, faixa_etaria_sel, df_saude_ref) if usar_saude else 0.0
        
        base_pss = vb + gdac + func_input
        pss = calcular_pss(base_pss, vinculo)
        
        base_irpf = max(0, (vb + gdac + func_input) - pss - (dep_ir * 189.59))
        ir, aliq, red = calcular_irpf(base_irpf, nome_cenario)
        
        bruto = vb + gdac + alim + func_input + pre_input + saude
        return {"VB": vb, "GDAC": gdac, "ALIM": alim, "FUNC": func_input, "PRE": pre_input, 
                "SAUDE": saude, "BRUTO": bruto, "IR": ir, "PSS": pss, "LIQ": bruto-ir-pss, "RED": red}
    except Exception as e:
        return None

res_25 = calcular("Tabela Vigente 01/01/2025")
res_26 = calcular("Lei nº 15.367/2026")

# --- 7. UI PRINCIPAL ---
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
            
            if res['FUNC'] > 0:
                st.write(f"Função Comissionada: R$ {formatar_br(res['FUNC'])}")
            
            if res['ALIM'] > 0:
                st.write(f"Auxílio Alimentação: R$ {formatar_br(res['ALIM'])}")
            
            if res['PRE'] > 0:
                st.write(f"Auxílio Pré-Escolar: R$ {formatar_br(res['PRE'])}")
            
            if res['SAUDE'] > 0:
                st.success(f"Saúde Suplementar: R$ {formatar_br(res['SAUDE'])}")

        with col_r:
            st.write("**Deduções:**")
            st.write(f"Previdência (PSS): R$ {formatar_br(res['PSS'])}")
            st.write(f"Imposto de Renda: R$ {formatar_br(res['IR'])}")
            if res['RED'] > 0:
                st.info(f"Redução Lei 15.270/25: R$ {formatar_br(res['RED'])}")
    else:
        st.error("Erro ao calcular os valores. Verifique se os arquivos CSV estão corretos.")

with t2:
    if res_25 and res_26:
        st.subheader("Evolução Salarial")
        dados_comp = {
            "Item": ["Vencimento Básico", "GDAC", "Auxílios/Saúde/Função", "TOTAL BRUTO", "PSS", "IRPF", "LÍQUIDO FINAL"],
            "Atual (2025)": [formatar_br(res_25['VB']), formatar_br(res_25['GDAC']), formatar_br(res_25['ALIM']+res_25['SAUDE']+res_25['PRE']+res_25['FUNC']), formatar_br(res_25['BRUTO']), f"-{formatar_br(res_25['PSS'])}", f"-{formatar_br(res_25['IR'])}", f"**{formatar_br(res_25['LIQ'])}**"],
            "Lei 15.367/26": [formatar_br(res_26['VB']), formatar_br(res_26['GDAC']), formatar_br(res_26['ALIM']+res_26['SAUDE']+res_26['PRE']+res_26['FUNC']), formatar_br(res_26['BRUTO']), f"-{formatar_br(res_26['PSS'])}", f"-{formatar_br(res_26['IR'])}", f"**{formatar_br(res_26['LIQ'])}**"]
        }
        st.table(pd.DataFrame(dados_comp))
        ganho = res_26['LIQ'] - res_25['LIQ']
        st.success(f"📈 Diferença Líquida: R$ {formatar_br(ganho)} ({(ganho/res_25['LIQ'])*100:.2f}%)")
    else:
        st.warning("Não foi possível calcular os valores comparativos.")

with t3:
    st.subheader("Base Normativa e Referências Legais")
    legislação = [
        ["Lei nº 8.112/1990", "Dispõe sobre o regime jurídico dos servidores públicos civis da União", "https://www.planalto.gov.br/ccivil_03/leis/l8112cons.htm"],
        ["Decreto nº 977/1993", "Dispõe sobre a assistência pré-escolar destinada aos dependentes dos servidores públicos da Administração Pública Federal", "https://www.planalto.gov.br/ccivil_03/decreto/antigos/d0977.htm"],
        ["Lei nº 11.233/2005", "Plano Especial de Cargos da Cultura e alterações posteriores.", "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2005/lei/L11233.htm"],
        ["Decreto nº 11.178/2022", "Estrutura regimental e cargos comissionados do IPHAN", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/d11178.htm"],
        ["Decreto nº 11.179/2022", "Estrutura regimental e cargos comissionados da Casa Rui Barbosa", "https://www.planalto.gov.br/ccivil_03/_Ato2019-2022/2022/Decreto/D11179.htm"],
        ["Decreto nº 11.203/2022", "Estrutura regimental e cargos comissionados da FCB", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/D11203.htm"],
        ["Decreto nº 11.233/2022", "Estrutura regimental e cargos comissionados da BN", "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/decreto/D11233.htm"],
        ["Instrução Normativa SGP/SEDGG/ME nº 97, de 26 de Dezembro de 2022", "Orientações sobre a saúde suplementar federal", "https://www.in.gov.br/en/web/dou/—/instrucao—normativa—sgp/sedgg/me—n—97—de—26—de—dezembro—de—2022—454820592"],
        ["Decreto nº 11.336/2023", "Estrutura regimental e cargos comissionados do MinC", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/decreto/d11336.htm"],
        ["Portaria MGI nº 2.829/2024", "Fixa valor mensal per capita para a assistência à saúde suplementar", "https://www.in.gov.br/en/web/dou/-/portaria-mgi-n-2.829-de-29-de-abril-de-2024-557063029"],
        ["Portaria MGI nº 2.897/2024", "Fixa o valor da Assistência Pré-Escolar.", "https://www.in.gov.br/en/web/dou/-/portaria-mgi-n-2.897-de-30-de-abril-de-2024-557088279"],
        ["Termo de Acordo nº 08/2024", "PGPE e PECs Setoriais - propostas dos servidores federais.", "https://www.condsef.org.br/documentos/pgpe-pecs-setoriais-termo-acordo-n-08-2024"],
        ["Decreto nº 12.335/2024", "Estrutura regimental e cargos comissionados do IBRAM", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2024/decreto/d12335.htm"],
        ["Portaria Interministerial MPS/MF nº 6/2025", "Reajuste do Regulamento da Previdência Social e Alíquotas PSS.", "https://www.in.gov.br/en/web/dou/-/portaria-interministerial-mps/mf-n-6-de-10-de-janeiro-de-2025-606526848"],
        ["Portaria MGI nº 9.888/2025", "Fixa o valor mensal do auxílio-alimentação.", "https://www.in.gov.br/web/dou/-/portaria/mgi-n-9.888-de-6-de-novembro-de-2025-667427345"],
        ["Lei nº 15.191/2025", "Modifica os valores da tabela progressiva mensal do IRPF.", "https://www.planalto.gov.br/ccivil_03/_Ato2023-2026/2025/Lei/L15191.htm"],
        ["Decreto nº 12.586/2025", "Estrutura regimental e cargos comissionados da FUNARTE", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/D12586.htm"],
        ["Lei nº 15.270/2025", "Zera o imposto de renda para rendimentos até R$ 5.000,00.", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15270.htm"],
        ["Lei nº 15.367/2026", "Reestruturação remuneratória entre outros...", "https://www.in.gov.br/web/dou/-/lei-n-15.367-de-30-de-marco-de-2026-696676817"]
    ]
    for item in legislação:
        st.markdown(f"**[{item[0]}]({item[2]})** — {item[1]}")

# --- 8. RODAPÉ ---
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray; font-size: 0.8em;'>"
    "Elaborado por 🚀GT de Elaboração das Emendas🚀 e 🔥Comando Nacional de Acompanhamento🔥"
    "</div>", 
    unsafe_allow_html=True
)
