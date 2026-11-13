from datetime import date

import pandas as pd

import analise

HOJE = date(2026, 11, 12)  # quinta-feira


def produto(codigo="001", estoque=10, minimo=5, custo=10.0, preco=20.0, prazo=3, nome="Item"):
    return {"codigo": codigo, "nome": nome, "categoria": "X", "estoque": estoque,
            "estoque_minimo": minimo, "custo": custo, "preco_venda": preco,
            "prazo_entrega_dias": prazo}


def vendas_de(*linhas):
    """linhas: (dias_atras, codigo, quantidade)."""
    return pd.DataFrame({
        "data": [pd.Timestamp(HOJE) - pd.Timedelta(days=d) for d, _, _ in linhas],
        "codigo": [c for _, c, _ in linhas],
        "quantidade": [q for _, _, q in linhas],
    })


def resumo(produtos, vendas, **kwargs):
    return analise.resumo_produtos(pd.DataFrame(produtos), vendas, HOJE, **kwargs)


def test_abaixo_minimo_trata_a_borda():
    r = resumo([produto("001", estoque=4), produto("002", estoque=5), produto("003", estoque=6)],
               vendas_de((1, "001", 1)))
    assert r["abaixo_minimo"].tolist() == [True, False, False]  # igual ao mínimo não é crítico


def test_cobertura_e_risco_de_ruptura():
    # 56 unidades em 28 dias = 2 por dia; estoque 4 dura 2 dias
    vendas = vendas_de((5, "001", 56))
    r = resumo([produto("001", estoque=4, prazo=3)], vendas)
    assert r.loc[0, "media_diaria"] == 2
    assert r.loc[0, "cobertura_dias"] == 2
    assert bool(r.loc[0, "risco_ruptura"]) is True
    r = resumo([produto("001", estoque=4, prazo=1)], vendas)
    assert bool(r.loc[0, "risco_ruptura"]) is False


def test_sem_vendas_cobertura_infinita_e_sem_risco():
    r = resumo([produto("001", estoque=4)], vendas_de((1, "002", 1)))
    assert r.loc[0, "cobertura_dias"] == float("inf")
    assert bool(r.loc[0, "risco_ruptura"]) is False


def test_item_parado_depende_dos_dias_sem_venda():
    vendas = vendas_de((40, "001", 1), (5, "002", 1))
    r = resumo([produto("001"), produto("002")], vendas, dias_parado=30)
    assert r["parado"].tolist() == [True, False]
    r = resumo([produto("001"), produto("002")], vendas, dias_parado=60)
    assert r["parado"].tolist() == [False, False]


def test_nunca_vendeu_com_estoque_e_parado_mas_sem_estoque_nao():
    r = resumo([produto("001", estoque=3), produto("002", estoque=0)], vendas_de((1, "003", 1)))
    assert r["parado"].tolist() == [True, False]


def test_sugestao_de_compra():
    # 2 por dia, prazo 3, alvo 14 -> demanda de 17 dias = 34; estoque 4 -> comprar 30
    r = resumo([produto("001", estoque=4, prazo=3)], vendas_de((5, "001", 56)),
               dias_cobertura_alvo=14)
    assert r.loc[0, "sugestao_compra"] == 30
    assert r.loc[0, "custo_compra"] == 300.0


def test_sugestao_nunca_e_negativa():
    r = resumo([produto("001", estoque=500)], vendas_de((5, "001", 56)))
    assert r.loc[0, "sugestao_compra"] == 0


def test_vendas_fora_da_janela_nao_entram_na_media():
    r = resumo([produto("001")], vendas_de((40, "001", 100)))
    assert r.loc[0, "unidades_janela"] == 0


def test_classe_abc():
    # receitas 850, 100 e 50 (preço igual): participação antes de cada item = 0%, 85%, 95%
    produtos = [produto("001", preco=10), produto("002", preco=10), produto("003", preco=10)]
    vendas = vendas_de((2, "001", 85), (2, "002", 10), (2, "003", 5))
    r = resumo(produtos, vendas)
    assert r["classe_abc"].tolist() == ["A", "B", "C"]


def test_projecao_nao_fica_negativa_e_comeca_no_estoque_atual():
    r = resumo([produto("001", estoque=10)], vendas_de((5, "001", 56)))  # 14 un./semana
    p = analise.projetar_estoque(r, semanas=3)
    assert p["estoque_projetado"].tolist() == [10.0, 0.0, 0.0, 0.0]


def test_vendas_semanais_so_semanas_completas():
    # hoje = quinta 12/11; última segunda completa de semana: 02/11 (semana 02-08/11)
    vendas = pd.DataFrame({
        "data": pd.to_datetime(["2026-10-19", "2026-10-26", "2026-11-02", "2026-11-10"]),
        "codigo": ["001"] * 4, "quantidade": [1, 2, 3, 4]})
    semanal = analise.vendas_semanais(vendas, HOJE)
    # 19/10 é a 1ª data (semana começa 19/10: completa); 09-15/11 está incompleta
    assert semanal["001"].tolist() == [1, 2, 3]
