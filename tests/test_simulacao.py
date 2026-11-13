from datetime import date

import pandas as pd

import simulacao

HOJE = date(2026, 11, 12)


def parametros():
    return pd.DataFrame({"codigo": ["001", "002"], "media_dia": [3.0, 0.5],
                         "perfil": ["alto giro", "parado"], "parado_ha_dias": [0, 20]})


def test_mesma_semente_gera_o_mesmo_historico():
    a = simulacao.gerar_vendas(parametros(), HOJE, semente=1)
    b = simulacao.gerar_vendas(parametros(), HOJE, semente=1)
    c = simulacao.gerar_vendas(parametros(), HOJE, semente=2)
    assert a.equals(b)
    assert not a.equals(c)


def test_nao_ha_vendas_no_domingo_nem_depois_de_ontem():
    v = simulacao.gerar_vendas(parametros(), HOJE)
    assert (v["data"].dt.day_of_week != 6).all()
    assert v["data"].max() < pd.Timestamp(HOJE)


def test_produto_parado_nao_vende_nos_ultimos_dias():
    v = simulacao.gerar_vendas(parametros(), HOJE)
    limite = pd.Timestamp(HOJE) - pd.Timedelta(days=20)  # últimos 20 dias: 22/10 a 11/11
    assert v[(v["codigo"] == "002") & (v["data"] >= limite)].empty


def test_quantidades_sao_inteiros_positivos():
    v = simulacao.gerar_vendas(parametros(), HOJE)
    assert (v["quantidade"] > 0).all()
    assert pd.api.types.is_integer_dtype(v["quantidade"])


def test_media_simulada_fica_perto_da_media_pedida():
    v = simulacao.gerar_vendas(parametros(), HOJE, semanas=52)
    media = v[v["codigo"] == "001"]["quantidade"].sum() / (52 * 7)
    assert 2.7 < media < 3.3
