from datetime import date

import pandas as pd
import pytest

import alertas
import analise

HOJE = date(2026, 11, 12)


def resumo_com_risco():
    produtos = pd.DataFrame({
        "codigo": ["001", "002"], "nome": ["Óleo", "Filtro"], "categoria": ["X", "X"],
        "estoque": [4, 100], "estoque_minimo": [5, 5], "custo": [10.0, 10.0],
        "preco_venda": [20.0, 20.0], "prazo_entrega_dias": [3, 3]})
    vendas = pd.DataFrame({"data": [pd.Timestamp("2026-11-05")] * 2,
                           "codigo": ["001", "002"], "quantidade": [56, 28]})
    return analise.resumo_produtos(produtos, vendas, HOJE)


def test_alerta_de_ruptura_menciona_o_produto_certo():
    lista = alertas.gerar_alertas(resumo_com_risco(), HOJE, HOJE)
    assert [a.tipo for a in lista] == ["ruptura_iminente"]
    assert "Óleo" in lista[0].titulo


def test_alerta_de_base_desatualizada_so_depois_do_limite():
    r = resumo_com_risco()
    no_limite = date(2026, 11, 5)       # 7 dias: ainda aceitável
    passou = date(2026, 11, 4)          # 8 dias: alerta
    assert "base_desatualizada" not in [a.tipo for a in alertas.gerar_alertas(r, no_limite, HOJE)]
    assert "base_desatualizada" in [a.tipo for a in alertas.gerar_alertas(r, passou, HOJE)]


def test_email_sem_alertas():
    assunto, corpo = alertas.montar_email([], HOJE)
    assert "0 alerta" in assunto
    assert "Nenhum alerta" in corpo


def test_email_lista_os_alertas():
    lista = alertas.gerar_alertas(resumo_com_risco(), date(2026, 11, 1), HOJE)
    assunto, corpo = alertas.montar_email(lista, HOJE)
    assert "2 alerta" in assunto
    assert "1. Atualize a base" in corpo and "2. Óleo" in corpo


def test_simulacao_de_envio_nao_exige_configuracao(capsys=None):
    assert alertas.enviar_email("assunto", "corpo", enviar=False) is False


def test_envio_real_sem_configuracao_falha_com_mensagem_clara(monkeypatch):
    for variavel in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_DESTINO"]:
        monkeypatch.delenv(variavel, raising=False)
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        alertas.enviar_email("assunto", "corpo", enviar=True)
