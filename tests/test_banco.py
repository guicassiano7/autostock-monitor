from datetime import date

import pandas as pd
import pytest

import analise
import banco
import simulacao

HOJE = date(2026, 11, 12)


def produtos_validos():
    return pd.DataFrame({
        "codigo": ["001", "002"], "nome": ["A", "B"], "categoria": ["X", "Y"],
        "estoque": [4, 18], "estoque_minimo": [10, 8], "custo": [35.9, 18.5],
        "preco_venda": [59.9, 29.9], "prazo_entrega_dias": [3, 4]})


def vendas_validas():
    return pd.DataFrame({"data": pd.to_datetime(["2026-11-10", "2026-11-11"]),
                         "codigo": ["001", "002"], "quantidade": [2, 3]})


def banco_carregado(tmp_path):
    conexao = banco.conectar(tmp_path / "t.db")
    banco.criar_tabelas(conexao)
    banco.carregar_produtos(conexao, produtos_validos())
    banco.carregar_vendas(conexao, vendas_validas())
    return conexao


def test_carga_e_leitura(tmp_path):
    conexao = banco_carregado(tmp_path)
    assert len(banco.ler_produtos(conexao)) == 2
    assert banco.ler_vendas(conexao)["quantidade"].sum() == 5
    conexao.close()


def test_carga_pode_ser_repetida_sem_duplicar(tmp_path):
    conexao = banco_carregado(tmp_path)
    banco.carregar_produtos(conexao, produtos_validos())
    banco.carregar_vendas(conexao, vendas_validas())
    assert len(banco.ler_produtos(conexao)) == 2
    assert len(banco.ler_vendas(conexao)) == 2
    conexao.close()


def test_upsert_atualiza_estoque(tmp_path):
    conexao = banco_carregado(tmp_path)
    novos = produtos_validos()
    novos.loc[0, "estoque"] = 99
    banco.carregar_produtos(conexao, novos)
    assert banco.ler_produtos(conexao).loc[0, "estoque"] == 99
    conexao.close()


def test_validacao_rejeita_codigo_duplicado():
    p = produtos_validos()
    p.loc[1, "codigo"] = "001"
    with pytest.raises(ValueError, match="duplicados"):
        banco.validar_produtos(p)


def test_validacao_rejeita_decimal_com_virgula():
    p = produtos_validos()
    p["custo"] = ["35,90", "18,50"]
    with pytest.raises(ValueError, match="ponto como separador"):
        banco.validar_produtos(p)


def test_validacao_rejeita_estoque_negativo():
    p = produtos_validos()
    p.loc[0, "estoque"] = -1
    with pytest.raises(ValueError, match="negativos"):
        banco.validar_produtos(p)


def test_vendas_de_produto_inexistente_sao_rejeitadas(tmp_path):
    conexao = banco_carregado(tmp_path)
    ruins = vendas_validas()
    ruins.loc[0, "codigo"] = "999"
    with pytest.raises(ValueError, match="999"):
        banco.carregar_vendas(conexao, ruins)
    assert len(banco.ler_vendas(conexao)) == 2  # o histórico anterior foi preservado
    conexao.close()


def test_normalizar_codigo():
    assert banco.normalizar_codigo(pd.Series(["1", " 02", "003"])).tolist() == ["001", "002", "003"]


def test_conferencia_cruzada_sql_x_pandas(tmp_path):
    """A mesma pergunta, respondida em SQL e em pandas, deve dar o mesmo número."""
    conexao = banco.conectar(tmp_path / "c.db")
    banco.criar_tabelas(conexao)
    produtos = banco.ler_produtos_csv()
    vendas = simulacao.gerar_vendas(simulacao.ler_parametros(), HOJE)
    banco.carregar_produtos(conexao, produtos)
    banco.carregar_vendas(conexao, vendas)

    r = analise.resumo_produtos(produtos, vendas, HOJE)
    inicio = pd.Timestamp(HOJE) - pd.Timedelta(days=28)
    sql = banco.unidades_vendidas_sql(conexao, inicio.date(), HOJE).set_index("codigo")["unidades"]
    pandas_ = r.set_index("codigo")["unidades_janela"]
    for codigo, unidades in sql.items():
        assert pandas_[codigo] == unidades
    assert pandas_.sum() == sql.sum()
    conexao.close()


def test_resumo_do_banco_somente_leitura(tmp_path):
    conexao = banco_carregado(tmp_path)
    conexao.close()
    assert banco.resumo_do_banco(tmp_path / "t.db") == {"controle": 0, "produtos": 2, "vendas": 2}
    with pytest.raises(FileNotFoundError):
        banco.resumo_do_banco(tmp_path / "nao_existe.db")
