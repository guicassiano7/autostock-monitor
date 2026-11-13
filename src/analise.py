"""Indicadores de estoque: o "cérebro" do projeto.

Todas as funções recebem DataFrames e devolvem DataFrames, sem ler arquivos
nem banco. Isso as torna fáceis de testar e de reutilizar (dashboard, alertas,
exportações).

Definições usadas em todo o projeto
-----------------------------------
media_diaria      unidades vendidas nas últimas `janela_dias` / `janela_dias`
                  (média móvel de 28 dias = 4 semanas)
cobertura_dias    estoque / media_diaria  (quantos dias o estoque dura)
abaixo_minimo     estoque < estoque_minimo (igual ao mínimo ainda não é crítico)
risco_ruptura     cobertura_dias <= prazo_entrega_dias (acaba antes, ou no
                  mesmo dia, em que o fornecedor entregaria)
parado            sem vendas há `dias_parado` dias ou mais, e com estoque > 0
sugestao_compra   demanda esperada em (prazo + dias_cobertura_alvo) - estoque
classe_abc        A: itens que somam até 80% da receita; B: até 95%; C: resto
"""

import math

import numpy as np
import pandas as pd

import config


def resumo_produtos(produtos, vendas, hoje,
                    janela_dias=config.JANELA_DIAS,
                    dias_parado=config.DIAS_PARADO,
                    dias_cobertura_alvo=config.DIAS_COBERTURA_ALVO):
    """Uma linha por produto, com todos os indicadores calculados."""
    hoje = pd.Timestamp(hoje).normalize()
    inicio = hoje - pd.Timedelta(days=janela_dias)

    na_janela = vendas[(vendas["data"] >= inicio) & (vendas["data"] < hoje)]
    unidades = na_janela.groupby("codigo")["quantidade"].sum()
    ultima_venda = vendas.groupby("codigo")["data"].max()

    r = produtos.reset_index(drop=True).copy()
    r["unidades_janela"] = r["codigo"].map(unidades).fillna(0).astype(int)
    r["ultima_venda"] = r["codigo"].map(ultima_venda)
    r["dias_sem_venda"] = (hoje - r["ultima_venda"]).dt.days

    r["media_diaria"] = r["unidades_janela"] / janela_dias
    r["media_semanal"] = r["media_diaria"] * 7
    demanda_positiva = r["media_diaria"].where(r["media_diaria"] > 0)
    r["cobertura_dias"] = (r["estoque"] / demanda_positiva).fillna(math.inf)

    r["valor_estoque"] = r["estoque"] * r["custo"]
    r["receita_janela"] = r["unidades_janela"] * r["preco_venda"]
    r["margem_janela"] = r["unidades_janela"] * (r["preco_venda"] - r["custo"])

    r["abaixo_minimo"] = r["estoque"] < r["estoque_minimo"]
    r["risco_ruptura"] = r["cobertura_dias"] <= r["prazo_entrega_dias"]
    nunca_vendeu = r["dias_sem_venda"].isna()
    r["parado"] = (nunca_vendeu | (r["dias_sem_venda"] >= dias_parado)) & (r["estoque"] > 0)

    necessidade = r["media_diaria"] * (r["prazo_entrega_dias"] + dias_cobertura_alvo) - r["estoque"]
    r["sugestao_compra"] = np.ceil(necessidade).clip(lower=0).astype(int)
    r["custo_compra"] = r["sugestao_compra"] * r["custo"]

    r["classe_abc"] = _classe_abc(r["receita_janela"])
    return r


def _classe_abc(receita):
    """Curva ABC pela participação acumulada na receita."""
    ordem = receita.sort_values(ascending=False)
    total = ordem.sum()
    if total == 0:
        return pd.Series("C", index=receita.index)
    participacao_antes = (ordem.cumsum() - ordem) / total
    classe = np.where(participacao_antes < 0.80, "A",
                      np.where(participacao_antes < 0.95, "B", "C"))
    return pd.Series(classe, index=ordem.index).reindex(receita.index)


def mais_vendidos(resumo, n=config.TOP_N_VENDIDOS):
    return resumo.nlargest(n, "unidades_janela")


def itens_parados(resumo):
    """Parados, começando pelos que mais prendem dinheiro."""
    return resumo[resumo["parado"]].sort_values("valor_estoque", ascending=False)


def itens_em_risco(resumo):
    """Itens que acabam antes da entrega do fornecedor, os mais urgentes primeiro."""
    return resumo[resumo["risco_ruptura"]].sort_values("cobertura_dias")


def vendas_semanais(vendas, hoje):
    """Unidades vendidas por semana (segunda a domingo) e por produto.

    Só entram semanas completas: a semana corrente e a primeira semana
    (quando incompleta) distorceriam o gráfico.
    """
    ultimo_dia = pd.Timestamp(hoje).normalize() - pd.Timedelta(days=1)
    v = vendas.copy()
    v["semana"] = v["data"].dt.to_period("W-SUN").dt.start_time
    tabela = v.groupby(["semana", "codigo"])["quantidade"].sum().unstack(fill_value=0)
    completas = (tabela.index >= vendas["data"].min()) & \
                (tabela.index + pd.Timedelta(days=6) <= ultimo_dia)
    return tabela[completas]


def projetar_estoque(resumo, semanas=config.HORIZONTE_SEMANAS):
    """Estoque projetado semana a semana, SEM nova compra.

    Modelo: estoque(s) = estoque atual - s x media_semanal, nunca abaixo de 0.
    É uma linha de base simples (média móvel), fácil de explicar e de testar.
    """
    quadros = []
    for semana in range(semanas + 1):
        projetado = (resumo["estoque"] - resumo["media_semanal"] * semana).clip(lower=0)
        quadros.append(pd.DataFrame({
            "codigo": resumo["codigo"],
            "nome": resumo["nome"],
            "semana": semana,
            "estoque_projetado": projetado.round(1),
        }))
    return pd.concat(quadros, ignore_index=True)
