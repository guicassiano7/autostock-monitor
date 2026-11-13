"""Camada de banco de dados (SQLite): criação, validação, carga e leitura.

Três tabelas:
    produtos   - cadastro e estoque atual de cada item
    vendas     - uma linha por (data, produto) com a quantidade vendida
    controle   - pares chave/valor (ex.: data da última atualização do estoque)
"""

import sqlite3
from pathlib import Path

import pandas as pd

import config

COLUNAS_PRODUTOS = ["codigo", "nome", "categoria", "estoque", "estoque_minimo",
                    "custo", "preco_venda", "prazo_entrega_dias"]
COLUNAS_NUMERICAS = ["estoque", "estoque_minimo", "custo", "preco_venda",
                     "prazo_entrega_dias"]
COLUNAS_VENDAS = ["data", "codigo", "quantidade"]

DDL = """
CREATE TABLE IF NOT EXISTS produtos (
    codigo              TEXT PRIMARY KEY,
    nome                TEXT NOT NULL,
    categoria           TEXT,
    estoque             INTEGER NOT NULL CHECK (estoque >= 0),
    estoque_minimo      INTEGER NOT NULL CHECK (estoque_minimo >= 0),
    custo               REAL NOT NULL CHECK (custo >= 0),
    preco_venda         REAL NOT NULL CHECK (preco_venda >= 0),
    prazo_entrega_dias  INTEGER NOT NULL CHECK (prazo_entrega_dias >= 0)
);
CREATE TABLE IF NOT EXISTS vendas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    data        TEXT NOT NULL,                      -- formato AAAA-MM-DD
    codigo      TEXT NOT NULL REFERENCES produtos(codigo),
    quantidade  INTEGER NOT NULL CHECK (quantidade > 0)
);
CREATE INDEX IF NOT EXISTS idx_vendas_codigo_data ON vendas (codigo, data);
CREATE TABLE IF NOT EXISTS controle (
    chave  TEXT PRIMARY KEY,
    valor  TEXT NOT NULL
);
"""


# --- Conexão e estrutura ----------------------------------------------------
def conectar(caminho=config.CAMINHO_BANCO):
    """Abre (ou cria) o banco. O caminho é parâmetro: o mesmo código serve
    para o banco de produção e para bancos temporários de teste."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.execute("PRAGMA foreign_keys = ON")  # o SQLite exige ligar isto
    return conexao


def criar_tabelas(conexao):
    with conexao:  # confirma (commit) ao fim, ou desfaz (rollback) se houver erro
        conexao.executescript(DDL)


# --- Leitura e validação de arquivos ---------------------------------------
def normalizar_codigo(serie):
    """'1' -> '001'. Feito uma única vez, logo após a leitura."""
    return serie.astype(str).str.strip().str.zfill(config.LARGURA_CODIGO)


def ler_produtos_csv(caminho=config.CAMINHO_PRODUTOS):
    produtos = pd.read_csv(caminho, dtype={"codigo": str})
    if "codigo" in produtos.columns:
        produtos["codigo"] = normalizar_codigo(produtos["codigo"])
    return produtos


def ler_vendas_csv(caminho=config.CAMINHO_VENDAS, mapa_colunas=None, dayfirst=False):
    """Lê um CSV de vendas. Para dados reais, use `mapa_colunas` para traduzir
    os nomes do sistema de vendas, por exemplo:
        {"Data da venda": "data", "Cód. produto": "codigo", "Qtd": "quantidade"}
    e `dayfirst=True` se as datas vierem como 31/12/2026."""
    vendas = pd.read_csv(caminho, dtype=str)
    if mapa_colunas:
        vendas = vendas.rename(columns=mapa_colunas)
    faltando = [c for c in COLUNAS_VENDAS if c not in vendas.columns]
    if faltando:
        raise ValueError(f"Colunas ausentes em vendas: {faltando}")
    vendas = vendas[COLUNAS_VENDAS].copy()
    vendas["data"] = pd.to_datetime(vendas["data"], dayfirst=dayfirst)
    vendas["codigo"] = normalizar_codigo(vendas["codigo"])
    vendas["quantidade"] = pd.to_numeric(vendas["quantidade"], errors="coerce")
    return vendas


def validar_produtos(produtos):
    """Levanta ValueError listando todos os problemas encontrados."""
    faltando = [c for c in COLUNAS_PRODUTOS if c not in produtos.columns]
    if faltando:
        raise ValueError(f"Colunas ausentes em produtos: {faltando}")
    problemas = []
    if produtos["codigo"].duplicated().any():
        problemas.append("códigos duplicados")
    if produtos[["codigo", "nome"]].isna().any().any():
        problemas.append("código ou nome vazio")
    for coluna in COLUNAS_NUMERICAS:
        convertida = pd.to_numeric(produtos[coluna], errors="coerce")
        if convertida.isna().any():
            problemas.append(f"'{coluna}' com valores vazios ou não numéricos "
                             "(use ponto como separador decimal)")
        elif (convertida < 0).any():
            problemas.append(f"'{coluna}' com valores negativos")
    if problemas:
        raise ValueError("Produtos inválidos: " + "; ".join(problemas))


def validar_vendas(vendas, codigos_validos):
    faltando = [c for c in COLUNAS_VENDAS if c not in vendas.columns]
    if faltando:
        raise ValueError(f"Colunas ausentes em vendas: {faltando}")
    problemas = []
    if vendas[COLUNAS_VENDAS].isna().any().any():
        problemas.append("valores vazios")
    elif (vendas["quantidade"] <= 0).any():
        problemas.append("quantidades menores ou iguais a zero")
    desconhecidos = set(vendas["codigo"]) - set(codigos_validos)
    if desconhecidos:
        problemas.append(f"códigos que não existem em produtos: {sorted(desconhecidos)}")
    if problemas:
        raise ValueError("Vendas inválidas: " + "; ".join(problemas))


# --- Carga ------------------------------------------------------------------
def carregar_produtos(conexao, produtos):
    """Insere ou atualiza (upsert) os produtos. Pode rodar várias vezes."""
    validar_produtos(produtos)
    linhas = produtos[COLUNAS_PRODUTOS].astype(object).values.tolist()
    with conexao:
        conexao.executemany(
            """
            INSERT INTO produtos (codigo, nome, categoria, estoque, estoque_minimo,
                                  custo, preco_venda, prazo_entrega_dias)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(codigo) DO UPDATE SET
                nome = excluded.nome,
                categoria = excluded.categoria,
                estoque = excluded.estoque,
                estoque_minimo = excluded.estoque_minimo,
                custo = excluded.custo,
                preco_venda = excluded.preco_venda,
                prazo_entrega_dias = excluded.prazo_entrega_dias
            """,
            linhas,
        )


def carregar_vendas(conexao, vendas):
    """Substitui todo o histórico de vendas (tudo ou nada, numa transação)."""
    codigos = [c for (c,) in conexao.execute("SELECT codigo FROM produtos")]
    validar_vendas(vendas, codigos)
    tabela = vendas[COLUNAS_VENDAS].copy()
    tabela["data"] = pd.to_datetime(tabela["data"]).dt.strftime("%Y-%m-%d")
    tabela["quantidade"] = tabela["quantidade"].astype(int)
    with conexao:
        conexao.execute("DELETE FROM vendas")
        conexao.executemany(
            "INSERT INTO vendas (data, codigo, quantidade) VALUES (?, ?, ?)",
            tabela.astype(object).values.tolist(),
        )


def definir_controle(conexao, chave, valor):
    with conexao:
        conexao.execute(
            "INSERT INTO controle (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (chave, str(valor)),
        )


# --- Leitura ----------------------------------------------------------------
def ler_controle(conexao, chave):
    linha = conexao.execute("SELECT valor FROM controle WHERE chave = ?", (chave,)).fetchone()
    if linha is None:
        raise KeyError(f"Chave '{chave}' não encontrada na tabela controle")
    return linha[0]


def ler_produtos(conexao):
    return pd.read_sql_query("SELECT * FROM produtos ORDER BY codigo", conexao)


def ler_vendas(conexao):
    return pd.read_sql_query(
        "SELECT data, codigo, quantidade FROM vendas ORDER BY data, codigo",
        conexao, parse_dates=["data"],
    )


def unidades_vendidas_sql(conexao, inicio, fim):
    """Unidades por produto entre `inicio` (inclusive) e `fim` (exclusive),
    calculadas em SQL. Serve de conferência cruzada para o cálculo em pandas."""
    return pd.read_sql_query(
        """
        SELECT codigo, SUM(quantidade) AS unidades
        FROM vendas
        WHERE data >= ? AND data < ?
        GROUP BY codigo
        ORDER BY codigo
        """,
        conexao, params=(str(inicio), str(fim)),
    )


def resumo_do_banco(caminho=config.CAMINHO_BANCO):
    """Conta as linhas de cada tabela, abrindo o banco SOMENTE para leitura."""
    caminho = Path(caminho).resolve()
    if not caminho.exists():
        raise FileNotFoundError(f"Banco não encontrado: {caminho}")
    conexao = sqlite3.connect(caminho.as_uri() + "?mode=ro", uri=True)
    try:
        tabelas = [n for (n,) in conexao.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {t: conexao.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in tabelas}
    finally:
        conexao.close()
