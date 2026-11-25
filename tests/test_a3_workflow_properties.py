"""
A3 | Teste além da cobertura | Fluxo de status (lógica) e propriedades com Hypothesis.

Rodar (da raiz do django-helpdesk):
    DJANGO_SETTINGS_MODULE=tests.test_settings PYTHONPATH=src:. pytest ../sac_qa_kit/tests/test_a3_workflow_properties.py
"""
from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import transaction
from django.urls import reverse
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from rest_framework.test import APIClient

from helpdesk import settings as hd
from helpdesk.models import FollowUp, Queue, Ticket, TicketChange, TicketDependency
from helpdesk.update_ticket import update_ticket
from helpdesk.user import HelpdeskUser

pytestmark = pytest.mark.django_db
User = get_user_model()
SEM_FIXTURE_LENTA = [HealthCheck.function_scoped_fixture, HealthCheck.too_slow]


@contextmanager
def rollback():
    with transaction.atomic():
        yield
        transaction.set_rollback(True)


def _transicoes_proibidas():
    fluxo, todos = hd.TICKET_STATUS_CHOICES_FLOW, [s for s, _ in hd.TICKET_STATUS_CHOICES]
    return [(a, b) for a in todos for b in todos if b not in fluxo[a]]


# --------------------------------------------------------------------------------------
# DEFEITOS CONFIRMADOS: o fluxo de status é só sugestão de interface
# --------------------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="F-08: update_ticket aceita as 10 transições que TICKET_STATUS_CHOICES_FLOW proíbe (ex.: Fechado -> Resolvido)")
def test_servidor_recusa_transicao_fora_do_fluxo():
    q = Queue.objects.create(title="q", slug="q")
    u = User.objects.create_user("s", password="x", is_staff=True, is_superuser=True)
    aceitas = []
    for de, para in _transicoes_proibidas():
        t = Ticket.objects.create(title="t", queue=q, status=de, submitter_email="a@x.invalid")
        update_ticket(u, t, comment="x", new_status=para, public=False)
        t.refresh_from_db()
        if t.status == para:
            aceitas.append((de, para))
    assert not aceitas, f"{len(aceitas)} de {len(_transicoes_proibidas())} transições proibidas foram aceitas: {aceitas}"


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="F-09: PATCH /api/tickets/<id>/ muda o status sem criar FollowUp nem TicketChange (sem trilha de auditoria)")
def test_mudanca_de_status_pela_api_deixa_trilha_de_auditoria():
    q = Queue.objects.create(title="q", slug="q")
    u = User.objects.create_user("s", password="x", is_staff=True, is_superuser=True)
    t = Ticket.objects.create(title="t", queue=q, status=Ticket.OPEN_STATUS, submitter_email="a@x.invalid")
    c = APIClient(); c.force_authenticate(u)
    assert c.patch(f"/api/tickets/{t.id}/", {"status": Ticket.CLOSED_STATUS}, format="json").status_code == 200
    # transição PERMITIDA (Aberto -> Fechado): mesmo assim precisa deixar rastro
    assert TicketChange.objects.filter(followup__ticket=t).exists() or FollowUp.objects.filter(ticket=t).exists()


# --------------------------------------------------------------------------------------
# PROPRIEDADES que passam hoje (e que matam mutantes de operador/condição)
# --------------------------------------------------------------------------------------
@settings(max_examples=60, deadline=None, suppress_health_check=SEM_FIXTURE_LENTA)
@given(statuses=st.lists(st.sampled_from([s for s, _ in hd.TICKET_STATUS_CHOICES]), max_size=5))
def test_propriedade_can_be_resolved_so_quando_nenhuma_dependencia_esta_aberta(statuses):
    """Oráculo independente: só se pode resolver quando TODA dependência está fora de OPEN_STATUSES."""
    with rollback():
        q = Queue.objects.create(title="q", slug="q")
        pai = Ticket.objects.create(title="pai", queue=q)
        for i, s in enumerate(statuses):
            filho = Ticket.objects.create(title=f"dep{i}", queue=q, status=s)
            TicketDependency.objects.create(ticket=pai, depends_on=filho)
        esperado = all(s not in Ticket.OPEN_STATUSES for s in statuses)
        assert pai.can_be_resolved is esperado


@settings(max_examples=80, deadline=None, suppress_health_check=SEM_FIXTURE_LENTA)
@given(titulo=st.text(max_size=400))
def test_propriedade_titulo_nunca_passa_de_200_e_preserva_o_prefixo(titulo):
    with rollback():
        q = Queue.objects.create(title="q", slug="q")
        t = Ticket.objects.create(title=titulo, queue=q)
        t.refresh_from_db()
        assert len(t.title) <= 200
        if len(titulo) <= 200:
            assert t.title == titulo
        else:
            assert t.title == titulo[:197] + "..."


@settings(max_examples=40, deadline=None, suppress_health_check=SEM_FIXTURE_LENTA)
@given(
    concedidas=st.lists(st.booleans(), min_size=3, max_size=3),       # permissão em cada uma de 3 filas
    fila_do_ticket=st.integers(0, 2),
    atribuicao=st.sampled_from(["ninguem", "o_usuario", "outro"]),
    superuser=st.booleans(),
)
def test_propriedade_acesso_a_ticket_segue_o_oraculo_e_consulta_bate_com_objeto(
        concedidas, fila_do_ticket, atribuicao, superuser, monkeypatch):
    """Modelo independente da regra de acesso. Também exige que accessible_tickets() (queryset) e
    can_access_ticket() (objeto) nunca discordem, que é a promessa do docstring."""
    monkeypatch.setattr(hd, "HELPDESK_ENABLE_PER_QUEUE_STAFF_PERMISSION", True)
    with rollback():
        filas = [Queue.objects.create(title=f"f{i}", slug=f"f{i}") for i in range(3)]
        user = User.objects.create_user("u", password="x", is_staff=True, is_superuser=superuser)
        outro = User.objects.create_user("o", password="x", is_staff=True)
        for fila, ok in zip(filas, concedidas):
            if ok:
                user.user_permissions.add(Permission.objects.get(codename=f"queue_access_{fila.slug}"))
        dono = {"ninguem": None, "o_usuario": user, "outro": outro}[atribuicao]
        t = Ticket.objects.create(title="t", queue=filas[fila_do_ticket], assigned_to=dono)

        user = User.objects.get(pk=user.pk)               # sem cache de permissões
        esperado = superuser or concedidas[fila_do_ticket] or atribuicao == "o_usuario"
        h = HelpdeskUser(user)
        assert h.can_access_ticket(t) is bool(esperado)
        assert h.accessible_tickets().filter(pk=t.pk).exists() is bool(esperado)


# Texto "de verdade" da internet: inclui controle, RTL, emoji, null e surrogates isolados são excluídos
# porque o cliente de teste não os transporta em UTF-8.
TEXTO = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=300)


@settings(max_examples=70, deadline=None, suppress_health_check=SEM_FIXTURE_LENTA)
@given(titulo=TEXTO, corpo=TEXTO, email=st.one_of(st.emails(), TEXTO), prioridade=st.integers(-3, 9))
def test_fuzz_formulario_publico_nunca_responde_5xx(client, titulo, corpo, email, prioridade):
    with rollback():
        fila = Queue.objects.create(title="Publica", slug="publica", allow_public_submission=True)
        r = client.post(reverse("helpdesk:home"), {"queue": fila.id, "title": titulo, "body": corpo,
                                                   "priority": prioridade, "submitter_email": email})
        assert r.status_code < 500, f"HTTP {r.status_code} para título={titulo!r} e-mail={email!r}"
        for t in Ticket.objects.all():
            assert len(t.title) <= 200
