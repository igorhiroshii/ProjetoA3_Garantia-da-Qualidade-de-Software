from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sac_omnichannel.cdc import avaliar_arrependimento, pode_arrepender

HOJE = date(2026, 11, 24)


def test_compra_recebida_hoje_ainda_pode_se_arrepender():
    assert pode_arrepender(recebimento=HOJE, hoje=HOJE) is True


def test_no_setimo_dia_ainda_pode_e_no_oitavo_nao():
    assert pode_arrepender(recebimento=date(2026, 11, 17), hoje=HOJE) is True      # 7 dias depois
    assert pode_arrepender(recebimento=date(2026, 11, 16), hoje=HOJE) is False     # 8 dias depois


@pytest.mark.parametrize("dias,esperado", [(0, True), (1, True), (6, True), (7, True), (8, False), (9, False), (30, False)])
def test_analise_de_valor_limite_do_prazo(dias, esperado):
    assert pode_arrepender(recebimento=HOJE - timedelta(days=dias), hoje=HOJE) is esperado


def test_recebimento_no_futuro_e_dado_invalido():
    with pytest.raises(ValueError, match="futuro"):
        pode_arrepender(recebimento=date(2026, 11, 25), hoje=HOJE)


@given(dias=st.integers(0, 3650))
def test_propriedade_pode_se_e_so_se_dias_ate_7_e_restantes_nunca_negativo(dias):
    r = avaliar_arrependimento(HOJE - timedelta(days=dias), HOJE)
    assert r.pode is (dias <= 7) and r.dias_restantes == max(7 - dias, 0) and r.dias_restantes >= 0


def test_resultado_informa_dias_decorridos_e_restantes():
    r = avaliar_arrependimento(HOJE - timedelta(days=3), HOJE)
    assert (r.pode, r.dias_decorridos, r.dias_restantes) == (True, 3, 4)
