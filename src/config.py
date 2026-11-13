"""Configurações centrais do projeto.

Todos os "números mágicos" (janelas de tempo, limites de alerta, caminhos)
ficam aqui, num único lugar. Para mudar uma regra de negócio, basta editar
este arquivo; o restante do código não precisa ser tocado.
"""

import os
from datetime import date
from pathlib import Path

# --- Caminhos ---------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "data"
CAMINHO_BANCO = PASTA_DADOS / "estoque.db"
CAMINHO_PRODUTOS = PASTA_DADOS / "produtos.csv"
CAMINHO_PARAMETROS = PASTA_DADOS / "parametros_simulacao.csv"
CAMINHO_VENDAS = PASTA_DADOS / "vendas.csv"
PASTA_SAIDAS = PASTA_DADOS / "saidas"

LARGURA_CODIGO = 3  # códigos como "001": preenchidos com zeros à esquerda

# Data fixa da demonstração: reproduz exatamente os números do README.
DATA_DEMO = date(2026, 11, 12)

# --- Simulação de vendas ----------------------------------------------------
SEMANAS_HISTORICO = 16
SEMENTE_PADRAO = 42
# Peso relativo de cada dia da semana (segunda=0 ... domingo=6).
# A oficina não abre no domingo e vende menos no sábado.
FATORES_DIA_SEMANA = [1.1, 1.0, 1.0, 1.0, 1.2, 0.7, 0.0]

# --- Regras de análise ------------------------------------------------------
JANELA_DIAS = 28            # média móvel: últimas 4 semanas
DIAS_PARADO = 30            # sem vender há tantos dias = item parado
TOP_N_VENDIDOS = 5
DIAS_COBERTURA_ALVO = 14    # ao comprar, cobrir este nº de dias após a entrega
HORIZONTE_SEMANAS = 4       # projeção de estoque

# --- Alertas ----------------------------------------------------------------
MAX_DIAS_BASE_DESATUALIZADA = 7
DIAS_BASE_DESATUALIZADA_NA_DEMO = 10  # na demonstração, a base "está atrasada"


def carregar_env(caminho=RAIZ / ".env"):
    """Lê um arquivo .env simples (CHAVE=valor) e coloca em os.environ.

    Serve para guardar a senha do e-mail fora do código. Variáveis que já
    existem no ambiente não são sobrescritas.
    """
    if not Path(caminho).exists():
        return
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())
