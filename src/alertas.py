"""Alertas de estoque e envio por e-mail.

Dois tipos de alerta:
    base_desatualizada  o estoque cadastrado não é atualizado há muitos dias
    ruptura_iminente    o produto acaba antes de o fornecedor conseguir entregar

O envio real de e-mail é opcional. Por padrão o texto só é mostrado na tela
(modo simulação), o que permite demonstrar o projeto sem expor senhas.
"""

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import pandas as pd

import analise
import config
import formatacao as fmt


@dataclass(frozen=True)
class Alerta:
    tipo: str
    titulo: str
    detalhe: str


def gerar_alertas(resumo, estoque_atualizado_em, hoje,
                  max_dias_base=config.MAX_DIAS_BASE_DESATUALIZADA):
    alertas = []

    dias = (pd.Timestamp(hoje).normalize() - pd.Timestamp(estoque_atualizado_em).normalize()).days
    if dias > max_dias_base:
        alertas.append(Alerta(
            "base_desatualizada",
            "Atualize a base de estoque",
            f"A última atualização foi há {dias} dias (limite: {max_dias_base}). "
            "Os alertas abaixo podem estar defasados até que a contagem seja refeita.",
        ))

    for linha in analise.itens_em_risco(resumo).itertuples():
        alertas.append(Alerta(
            "ruptura_iminente",
            f"{linha.nome} ({linha.codigo}) está acabando",
            f"Estoque de {linha.estoque} un. dura cerca de {fmt.cobertura(linha.cobertura_dias)}, "
            f"e o fornecedor leva {linha.prazo_entrega_dias} dias. "
            f"Sugestão: comprar {linha.sugestao_compra} un. ({fmt.reais(linha.custo_compra)}).",
        ))
    return alertas


def montar_email(alertas, hoje):
    """Devolve (assunto, corpo) em texto simples."""
    data = pd.Timestamp(hoje).strftime("%d/%m/%Y")
    assunto = f"[AutoStock] {len(alertas)} alerta(s) de estoque - {data}"
    if not alertas:
        return assunto, f"Nenhum alerta de estoque em {data}."
    blocos = [f"Resumo de alertas de estoque - {data}", ""]
    for numero, alerta in enumerate(alertas, start=1):
        blocos += [f"{numero}. {alerta.titulo}", f"   {alerta.detalhe}", ""]
    return assunto, "\n".join(blocos).rstrip()


def enviar_email(assunto, corpo, enviar=False):
    """Envia o e-mail por SMTP, ou apenas o exibe quando `enviar` é False.

    Configuração por variáveis de ambiente (ou arquivo .env):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_DESTINO.
    Devolve True se enviou, False se foi só simulação.
    """
    if not enviar:
        print("--- E-mail (simulação, nada foi enviado) ---")
        print(f"Assunto: {assunto}\n\n{corpo}")
        return False

    variaveis = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_DESTINO"]
    ausentes = [v for v in variaveis if not os.environ.get(v)]
    if ausentes:
        raise RuntimeError(f"Variáveis de ambiente ausentes: {ausentes}. Veja .env.example")

    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = os.environ["SMTP_USER"]
    mensagem["To"] = os.environ["EMAIL_DESTINO"]
    mensagem.set_content(corpo)

    porta = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(os.environ["SMTP_HOST"], porta, timeout=30) as servidor:
        servidor.starttls()
        servidor.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        servidor.send_message(mensagem)
    return True
