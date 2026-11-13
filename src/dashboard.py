"""Dashboard do AutoStock Monitor (Streamlit).

Como rodar, a partir da raiz do projeto:
    python src/pipeline.py          # gera dados e banco (uma vez)
    streamlit run src/dashboard.py

Princípio de design: responder em poucos segundos às perguntas do dono da
oficina: quanto dinheiro está parado? o que está para acabar? o que não vende?
"""

from datetime import date

import pandas as pd
import streamlit as st

import alertas
import analise
import banco
import config
import formatacao as fmt
import pipeline

st.set_page_config(page_title="AutoStock Monitor", page_icon="🛢️", layout="wide")


def carregar_dados():
    if not config.CAMINHO_BANCO.exists():
        # Primeira execução (ex.: na versão online): gera dados simulados e banco.
        with st.spinner("Preparando os dados da demonstração..."):
            pipeline.executar(hoje=config.DATA_DEMO, imprimir=False)
    conexao = banco.conectar(config.CAMINHO_BANCO)
    try:
        produtos = banco.ler_produtos(conexao)
        vendas = banco.ler_vendas(conexao)
        hoje = date.fromisoformat(banco.ler_controle(conexao, "data_referencia"))
        atualizado_em = date.fromisoformat(banco.ler_controle(conexao, "estoque_atualizado_em"))
    finally:
        conexao.close()
    return produtos, vendas, hoje, atualizado_em


produtos, vendas, hoje, atualizado_em = carregar_dados()

# --- Barra lateral: um único parâmetro, para manter o painel simples --------
dias_parado = st.sidebar.slider(
    "Item parado após quantos dias sem venda?", min_value=7, max_value=90,
    value=config.DIAS_PARADO, step=1)
st.sidebar.caption("A projeção usa a média de vendas das últimas 4 semanas.")

resumo = analise.resumo_produtos(produtos, vendas, hoje, dias_parado=dias_parado)
em_risco = analise.itens_em_risco(resumo)
parados = analise.itens_parados(resumo)
lista_alertas = alertas.gerar_alertas(resumo, atualizado_em, hoje)

# --- Cabeçalho --------------------------------------------------------------
st.title("AutoStock Monitor")
st.caption(f"Oficina de troca de óleo e serviços automotivos · dados simulados · "
           f"referência: {hoje:%d/%m/%Y} · estoque atualizado em {atualizado_em:%d/%m/%Y}")

# --- Indicadores-chave ------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Valor em estoque (custo)", fmt.reais(resumo["valor_estoque"].sum()))
c2.metric("Acabando antes da entrega", len(em_risco),
          help="Itens cuja cobertura em dias é menor ou igual ao prazo do fornecedor.")
c3.metric("Abaixo do estoque mínimo", int(resumo["abaixo_minimo"].sum()),
          help="Regra clássica: estoque menor que o mínimo cadastrado.")
c4.metric("Itens parados", len(parados),
          help=f"Sem vendas há {dias_parado} dias ou mais.")
c4.caption(f"{fmt.reais(parados['valor_estoque'].sum())} parados")

# --- Alertas ----------------------------------------------------------------
st.subheader("Alertas")
if lista_alertas:
    for alerta in lista_alertas:
        st.warning(f"**{alerta.titulo}.** {alerta.detalhe}")
else:
    st.success("Nenhum alerta no momento.")

st.divider()

# --- Mais vendidos e parados -----------------------------------------------
esquerda, direita = st.columns(2)

with esquerda:
    st.subheader("Mais vendidos (últimas 4 semanas)")
    top = analise.mais_vendidos(resumo)
    st.bar_chart(top.set_index("nome")["unidades_janela"].rename("Unidades vendidas"))

with direita:
    st.subheader("Parados em estoque")
    if parados.empty:
        st.success("Nenhum item parado.")
    else:
        tabela = pd.DataFrame({
            "Produto": parados["nome"],
            "Estoque": parados["estoque"],
            "Dias sem venda": parados["dias_sem_venda"].fillna(-1).astype(int),
            "Dinheiro parado": parados["valor_estoque"].map(fmt.reais),
        })
        st.dataframe(tabela, hide_index=True)

st.divider()

# --- Projeção semanal -------------------------------------------------------
st.subheader("Projeção semanal")
nomes = resumo["nome"].tolist()
padrao = nomes.index(em_risco.iloc[0]["nome"]) if not em_risco.empty else 0
escolhido = st.selectbox("Produto", nomes, index=padrao)
linha = resumo[resumo["nome"] == escolhido].iloc[0]

graf_hist, graf_proj = st.columns(2)

with graf_hist:
    st.caption("Vendas por semana (últimas 8 semanas completas)")
    semanais = analise.vendas_semanais(vendas, hoje)
    serie = semanais[linha["codigo"]].tail(8) if linha["codigo"] in semanais.columns else None
    if serie is not None and not serie.empty:
        st.bar_chart(serie.rename("Unidades"))
    else:
        st.info("Sem vendas registradas para este produto.")

with graf_proj:
    st.caption("Estoque projetado nas próximas semanas (sem nova compra)")
    projecao = analise.projetar_estoque(resumo)
    serie = projecao[projecao["codigo"] == linha["codigo"]].set_index("semana")["estoque_projetado"]
    st.line_chart(serie.rename("Estoque projetado"))

# --- Sugestão de compra -----------------------------------------------------
st.subheader("Sugestão de compra")
if em_risco.empty:
    st.success("Nenhuma compra urgente.")
else:
    compra = pd.DataFrame({
        "Produto": em_risco["nome"],
        "Estoque": em_risco["estoque"],
        "Dura (dias)": em_risco["cobertura_dias"].round(1),
        "Prazo do fornecedor (dias)": em_risco["prazo_entrega_dias"],
        "Comprar (un.)": em_risco["sugestao_compra"],
        "Custo estimado": em_risco["custo_compra"].map(fmt.reais),
    })
    st.dataframe(compra, hide_index=True)
    st.caption(f"Custo total estimado: {fmt.reais(em_risco['custo_compra'].sum())}. "
               f"A sugestão cobre o prazo do fornecedor mais {config.DIAS_COBERTURA_ALVO} dias de vendas.")
