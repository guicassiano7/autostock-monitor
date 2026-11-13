"""Funções pequenas para exibir números no padrão brasileiro."""

import math


def reais(valor):
    """1234.5 -> 'R$ 1.234,50'."""
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {texto}"


def numero(valor, casas=1):
    """3.14159 -> '3,1'."""
    return f"{valor:.{casas}f}".replace(".", ",")


def cobertura(dias):
    """Cobertura em dias; sem vendas, a cobertura é infinita."""
    if dias is None or (isinstance(dias, float) and math.isinf(dias)):
        return "sem vendas"
    return f"{numero(dias)} dias"
