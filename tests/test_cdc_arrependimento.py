from datetime import date

from sac_omnichannel.cdc import pode_arrepender

HOJE = date(2026, 11, 24)


def test_compra_recebida_hoje_ainda_pode_se_arrepender():
    assert pode_arrepender(recebimento=HOJE, hoje=HOJE) is True
