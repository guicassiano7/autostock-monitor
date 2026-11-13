"""Geração do histórico de vendas simulado.

Ideia central: a venda diária de cada produto é uma contagem de eventos
(clientes que compram o item). Contagens desse tipo costumam ser bem descritas
pela distribuição de Poisson, cujo único parâmetro é a média (lambda).

    quantidade vendida no dia ~ Poisson(media_dia x fator_do_dia_da_semana)

Produtos "parados" têm as vendas zeradas nos últimos N dias, para que exista
um item realmente parado a ser descoberto pela análise.
"""

from datetime import date

import numpy as np
import pandas as pd

import config

COLUNAS_PARAMETROS = ["codigo", "media_dia", "perfil", "parado_ha_dias"]


def ler_parametros(caminho=config.CAMINHO_PARAMETROS):
    """Lê o arquivo com a 'verdade secreta' da simulação (média por produto)."""
    parametros = pd.read_csv(caminho, dtype={"codigo": str})
    faltando = [c for c in COLUNAS_PARAMETROS if c not in parametros.columns]
    if faltando:
        raise ValueError(f"Colunas ausentes em parametros_simulacao: {faltando}")
    parametros["codigo"] = parametros["codigo"].str.strip().str.zfill(config.LARGURA_CODIGO)
    return parametros


def gerar_vendas(parametros, hoje, semanas=config.SEMANAS_HISTORICO,
                 semente=config.SEMENTE_PADRAO):
    """Devolve um DataFrame com colunas data, codigo, quantidade.

    O histórico cobre `semanas` semanas e termina no dia anterior a `hoje`.
    Só aparecem linhas com quantidade > 0 (como numa exportação de vendas).
    """
    n_dias = semanas * 7
    datas = pd.date_range(end=pd.Timestamp(hoje) - pd.Timedelta(days=1),
                          periods=n_dias, freq="D")

    # Fator do dia da semana, normalizado para ter média 1: assim a média
    # diária de cada produto continua sendo a do arquivo de parâmetros.
    fatores = np.array(config.FATORES_DIA_SEMANA, dtype=float)
    fatores = fatores / fatores.mean()
    fator_do_dia = fatores[datas.day_of_week.to_numpy()]

    medias = parametros["media_dia"].to_numpy(dtype=float)
    lam = np.outer(fator_do_dia, medias)

    # Zera os últimos `parado_ha_dias` dias dos produtos parados.
    dias_ate_o_fim = (n_dias - 1) - np.arange(n_dias)
    parado_ha = parametros["parado_ha_dias"].to_numpy(dtype=int)
    lam[dias_ate_o_fim[:, None] < parado_ha[None, :]] = 0.0

    gerador = np.random.default_rng(semente)
    quantidades = gerador.poisson(lam)

    i_dia, i_produto = np.nonzero(quantidades)
    vendas = pd.DataFrame({
        "data": datas[i_dia],
        "codigo": parametros["codigo"].to_numpy()[i_produto],
        "quantidade": quantidades[i_dia, i_produto].astype(int),
    })
    return vendas.sort_values(["data", "codigo"]).reset_index(drop=True)


def data_referencia(valor=None):
    """Converte texto 'AAAA-MM-DD' em date; sem valor, usa a data de hoje."""
    return date.fromisoformat(valor) if valor else date.today()
