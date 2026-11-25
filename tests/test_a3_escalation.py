"""
A3 | Teste além da cobertura | Escalonamento por prazo (lógica/SLA).

Todos os testes marcados com xfail(strict=True) descrevem um DEFEITO CONFIRMADO por execução.
strict=True significa: enquanto o defeito existe o teste "falha como esperado" e a suíte fica verde;
no dia em que o defeito for corrigido o teste passa, vira XPASS e QUEBRA a suíte, obrigando a
remover o xfail. O defeito não some em silêncio.

Rodar (da raiz do django-helpdesk):
    DJANGO_SETTINGS_MODULE=tests.test_settings PYTHONPATH=src:. pytest ../sac_qa_kit/tests/test_a3_escalation.py
"""
import datetime as dt
from contextlib import contextmanager
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import transaction
from django.test import override_settings
from django.utils import timezone
from freezegun import freeze_time
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from helpdesk.models import EscalationExclusion, Queue, Ticket

pytestmark = pytest.mark.django_db
AGORA = "2026-11-24 15:00:00"


def _fila(slug, dias):
    return Queue.objects.create(title=slug, slug=slug, escalate_days=dias)


def _ticket(fila, criado, prioridade=3):
    t = Ticket.objects.create(title="t", queue=fila, priority=prioridade)
    Ticket.objects.filter(pk=t.pk).update(created=criado)
    return t


def _escalona():
    call_command("escalate_tickets", stdout=StringIO())


@contextmanager
def rollback():
    """Um banco limpo por exemplo do Hypothesis (savepoint desfeito no fim)."""
    with transaction.atomic():
        yield
        transaction.set_rollback(True)


# --------------------------------------------------------------------------------------
# Defeitos confirmados (cada um com a evidência da execução em RELATORIO.md)
# --------------------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="F-01: o comando ignora EscalationExclusion.queues e aplica a exclusão a TODAS as filas")
@freeze_time(AGORA)
def test_exclusao_de_uma_fila_nao_pode_antecipar_escalonamento_de_outra():
    varejo, banco = _fila("varejo", 3), _fila("banco", 3)
    excl = EscalationExclusion.objects.create(name="so varejo", date=dt.date(2026, 11, 22))
    excl.queues.add(varejo)
    t = _ticket(banco, timezone.now() - dt.timedelta(days=2, hours=12))
    _escalona()
    t.refresh_from_db()
    assert t.priority == 3


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="F-02: dias de exclusão ENCURTAM o prazo em vez de estendê-lo")
@freeze_time(AGORA)
def test_fim_de_semana_nao_pode_antecipar_escalonamento():
    fila = _fila("energia-comercial", 3)
    for dia in (22, 23):
        EscalationExclusion.objects.create(name="fim de semana", date=dt.date(2026, 11, dia))
    t = _ticket(fila, timezone.now() - dt.timedelta(days=2, hours=12))
    _escalona()
    t.refresh_from_db()
    assert t.priority == 3


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="F-03: o comando escalona em dia marcado como 'escalonamento não deve ocorrer'")
@freeze_time(AGORA)
def test_nao_escalona_em_dia_de_exclusao():
    fila = _fila("telecom", 1)
    EscalationExclusion.objects.create(name="feriado hoje", date=dt.date(2026, 11, 24))
    t = _ticket(fila, timezone.now() - dt.timedelta(days=5))
    _escalona()
    t.refresh_from_db()
    assert t.priority == 3


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="F-01/F-02 em forma de propriedade: nenhum ticket pode escalar com menos de escalate_days dias corridos")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(dias=st.integers(1, 5),
       idade_horas=st.integers(0, 24 * 8),
       excluidos=st.sets(st.integers(0, 7), max_size=6))
def test_propriedade_nunca_escalona_antes_do_prazo_em_dias_corridos(dias, idade_horas, excluidos):
    """Invariante defensável em QUALQUER interpretação de dia útil: dias úteis nunca são menos que
    dias corridos, então um ticket só pode escalar depois de `escalate_days` dias corridos."""
    with rollback(), freeze_time(AGORA):
        fila = _fila("prop", dias)
        for d in excluidos:
            EscalationExclusion.objects.create(name="x", date=(timezone.now() - dt.timedelta(days=d)).date())
        t = _ticket(fila, timezone.now() - dt.timedelta(hours=idade_horas))
        _escalona()
        t.refresh_from_db()
        if t.priority == 2:                       # escalou
            assert idade_horas >= dias * 24, f"escalou com {idade_horas}h; prazo era {dias} dia(s)"


# --------------------------------------------------------------------------------------
# Comportamentos que PASSAM hoje e que o produto precisa manter (guardas de regressão)
# --------------------------------------------------------------------------------------
@freeze_time(AGORA)
def test_prioridade_1_nunca_e_escalonada_nem_gera_alerta():
    """Não é bug do código (é decisão de projeto), mas é RISCO de negócio: emergência prioridade 1
    parada há 30 dias fica sem nenhum alerta automático. Fixado aqui para virar decisão consciente."""
    t = _ticket(_fila("urgente", 1), timezone.now() - dt.timedelta(days=30), prioridade=1)
    _escalona()
    t.refresh_from_db()
    assert t.priority == 1 and t.last_escalation is None


@freeze_time(AGORA)
def test_ticket_em_espera_nao_escalona():
    t = _ticket(_fila("espera", 1), timezone.now() - dt.timedelta(days=10))
    Ticket.objects.filter(pk=t.pk).update(on_hold=True)
    _escalona()
    t.refresh_from_db()
    assert t.priority == 3


@freeze_time(AGORA)
def test_ticket_fechado_nao_escalona():
    t = _ticket(_fila("fechado", 1), timezone.now() - dt.timedelta(days=10))
    Ticket.objects.filter(pk=t.pk).update(status=Ticket.CLOSED_STATUS)
    _escalona()
    t.refresh_from_db()
    assert t.priority == 3


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="F-05: o comando usa a data em UTC (timezone.now().date()), não a do fuso da operação")
@override_settings(TIME_ZONE="America/Sao_Paulo")
@freeze_time("2026-11-25 01:30:00")   # 22h30 de 24/11 em Brasília; já é 25/11 em UTC
def test_ticket_de_10_minutos_nao_escalona_por_causa_de_feriado_no_fuso_da_operacao():
    """Com o feriado em 24/11 (data local) e o relógio em UTC, o comando calcula 0 dias úteis e escalona
    até um ticket aberto há 10 minutos. Com a data local (24/11) a janela não incluiria o feriado."""
    fila = _fila("energia-local", 1)
    EscalationExclusion.objects.create(name="feriado local", date=dt.date(2026, 11, 24))
    t = _ticket(fila, timezone.now() - dt.timedelta(minutes=10))
    _escalona()
    t.refresh_from_db()
    assert t.priority == 3
