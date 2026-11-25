"""Direito de arrependimento (CDC, art. 49): 7 dias corridos a contar do recebimento.

Premissas do grupo (validar com o jurídico): o dia do recebimento é o dia 0; o dia 7 ainda vale;
não há prorrogação para fim de semana ou feriado.
"""
from dataclasses import dataclass
from datetime import date

PRAZO_DIAS = 7


@dataclass(frozen=True)
class Arrependimento:
    pode: bool
    dias_decorridos: int
    dias_restantes: int


def avaliar_arrependimento(recebimento: date, hoje: date) -> Arrependimento:
    dias = (hoje - recebimento).days
    if dias < 0:
        raise ValueError("data de recebimento no futuro")
    return Arrependimento(pode=dias <= PRAZO_DIAS, dias_decorridos=dias, dias_restantes=max(PRAZO_DIAS - dias, 0))


def pode_arrepender(recebimento: date, hoje: date) -> bool:
    return avaliar_arrependimento(recebimento, hoje).pode
