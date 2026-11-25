from datetime import date

from sac_omnichannel.cdc import pode_arrepender

HOJE = date(2026, 11, 24)


def test_compra_recebida_hoje_ainda_pode_se_arrepender():
    assert pode_arrepender(recebimento=HOJE, hoje=HOJE) is True


def test_no_setimo_dia_ainda_pode_e_no_oitavo_nao():
    assert pode_arrepender(recebimento=date(2026, 11, 17), hoje=HOJE) is True      # 7 dias depois
    assert pode_arrepender(recebimento=date(2026, 11, 16), hoje=HOJE) is False     # 8 dias depois
