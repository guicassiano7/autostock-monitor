"""Pipeline completo: simula (ou lê) vendas, carrega o banco, calcula os
indicadores, exporta tabelas e gera os alertas.

Uso (a partir da raiz do projeto):
    python src/pipeline.py                       # demonstração completa
    python src/pipeline.py --hoje 2026-11-12     # data fixa (reproduzível)
    python src/pipeline.py --vendas-csv data/real/vendas.csv
    python src/pipeline.py --enviar-email        # envia de verdade (exige .env)
"""

import argparse
from datetime import date, timedelta

import analise
import alertas
import banco
import config
import simulacao


def executar(hoje=None, semente=config.SEMENTE_PADRAO, vendas_csv=None,
             estoque_atualizado_em=None, enviar_email=False,
             caminho_banco=config.CAMINHO_BANCO, pasta_saidas=config.PASTA_SAIDAS,
             imprimir=True):
    config.carregar_env()
    hoje = hoje or date.today()
    estoque_atualizado_em = estoque_atualizado_em or (
        hoje - timedelta(days=config.DIAS_BASE_DESATUALIZADA_NA_DEMO))

    # 1. Dados de entrada
    produtos = banco.ler_produtos_csv(config.CAMINHO_PRODUTOS)
    if vendas_csv:
        vendas = banco.ler_vendas_csv(vendas_csv)
    else:
        parametros = simulacao.ler_parametros(config.CAMINHO_PARAMETROS)
        vendas = simulacao.gerar_vendas(parametros, hoje, semente=semente)
        vendas.to_csv(config.CAMINHO_VENDAS, index=False)

    # 2. Banco de dados
    conexao = banco.conectar(caminho_banco)
    try:
        banco.criar_tabelas(conexao)
        banco.carregar_produtos(conexao, produtos)
        banco.carregar_vendas(conexao, vendas)
        banco.definir_controle(conexao, "data_referencia", hoje.isoformat())
        banco.definir_controle(conexao, "estoque_atualizado_em", estoque_atualizado_em.isoformat())
    finally:
        conexao.close()

    # 3. Indicadores
    resumo = analise.resumo_produtos(produtos, vendas, hoje)
    projecao = analise.projetar_estoque(resumo)
    semanais = analise.vendas_semanais(vendas, hoje)

    # 4. Exportações (úteis para Power BI ou Excel)
    pasta_saidas.mkdir(parents=True, exist_ok=True)
    resumo.to_csv(pasta_saidas / "resumo_produtos.csv", index=False)
    projecao.to_csv(pasta_saidas / "projecao_estoque.csv", index=False)
    semanais.stack().rename("unidades").reset_index().to_csv(
        pasta_saidas / "vendas_semanais.csv", index=False)

    # 5. Alertas
    lista = alertas.gerar_alertas(resumo, estoque_atualizado_em, hoje)
    assunto, corpo = alertas.montar_email(lista, hoje)

    if imprimir:
        print("Banco:", banco.resumo_do_banco(caminho_banco))
        colunas = ["codigo", "nome", "estoque", "media_diaria", "cobertura_dias",
                   "prazo_entrega_dias", "risco_ruptura", "parado", "classe_abc"]
        print("\n", resumo[colunas].round(2).to_string(index=False), "\n", sep="")
    alertas.enviar_email(assunto, corpo, enviar=enviar_email)
    return resumo, lista


def ler_argumentos():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hoje", type=date.fromisoformat, help="data de referência (AAAA-MM-DD)")
    p.add_argument("--semente", type=int, default=config.SEMENTE_PADRAO)
    p.add_argument("--vendas-csv", help="usar este CSV (data,codigo,quantidade) em vez da simulação")
    p.add_argument("--estoque-atualizado-em", type=date.fromisoformat,
                   help="data da última contagem de estoque (AAAA-MM-DD)")
    p.add_argument("--enviar-email", action="store_true", help="enviar o e-mail de verdade")
    return p.parse_args()


if __name__ == "__main__":
    args = ler_argumentos()
    executar(hoje=args.hoje, semente=args.semente, vendas_csv=args.vendas_csv,
             estoque_atualizado_em=args.estoque_atualizado_em,
             enviar_email=args.enviar_email)
