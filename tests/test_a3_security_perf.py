"""
A3 | Seguro e sustentável | Controle de acesso entre filas, vazamento (LGPD) e orçamento de queries.

Dois tipos de teste aqui:
  * xfail(strict=True, raises=...)  -> DEFEITO confirmado; vira XPASS (e quebra a suíte) quando corrigido.
  * teste comum                     -> comportamento que RESISTIU à auditoria e deve continuar assim.

Rodar (da raiz do django-helpdesk):
    DJANGO_SETTINGS_MODULE=tests.test_settings PYTHONPATH=src:. pytest ../sac_qa_kit/tests/test_a3_security_perf.py
"""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from helpdesk import settings as hd_settings
from helpdesk.models import FollowUp, Queue, Ticket
from helpdesk.update_ticket import update_ticket

pytestmark = pytest.mark.django_db
User = get_user_model()
CPF_SINTETICO = "123.456.789-00"      # dígito verificador inválido de propósito


@pytest.fixture(autouse=True)
def por_fila(monkeypatch):
    """Liga o isolamento por fila (é o que a operação multi-setor precisa)."""
    monkeypatch.setattr(hd_settings, "HELPDESK_ENABLE_PER_QUEUE_STAFF_PERMISSION", True)


@pytest.fixture
def cenario(db):
    """Varejo (pública), Banco Transacional e Ouvidoria (privadas), cada uma com seu atendente."""
    q = {
        "varejo": Queue.objects.create(title="Varejo", slug="varejo", allow_public_submission=True),
        "banco": Queue.objects.create(title="Banco Transacional", slug="banco", allow_public_submission=False),
        "ouvidoria": Queue.objects.create(title="Ouvidoria", slug="ouvidoria", allow_public_submission=False),
    }
    u = {}
    for nome in q:
        user = User.objects.create_user(f"ag_{nome}", password="x", is_staff=True)
        g = Group.objects.create(name=f"g_{nome}")
        g.permissions.add(Permission.objects.get(codename=f"queue_access_{nome}"))
        user.groups.add(g)
        u[nome] = user
    t = {n: Ticket.objects.create(title=f"SIGILO-{n.upper()}", queue=q[n], submitter_email=f"{n}@x.invalid",
                                  description=f"corpo sigiloso {n} {CPF_SINTETICO}") for n in q}
    return q, u, t


# --------------------------------------------------------------------------------------
# DEFEITOS CONFIRMADOS
# --------------------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="F-06: o formulário público deixa o cliente escolher prioridade 1 (máxima)")
def test_anonimo_nao_pode_abrir_ticket_com_prioridade_maxima(client, cenario):
    q, _, _ = cenario
    client.post(reverse("helpdesk:home"), {"queue": q["varejo"].id, "title": "qualquer coisa", "body": "oi",
                                           "priority": 1, "submitter_email": "c@x.invalid"})
    assert Ticket.objects.get(title="qualquer coisa").priority != 1


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="F-04: apagar filas em lote (ação 'excluir selecionados' do admin) deixa a permissão queue_access_* órfã")
def test_apagar_fila_em_lote_remove_a_permissao():
    q = Queue.objects.create(title="Temporaria", slug="temp-a")
    Queue.objects.filter(pk=q.pk).delete()
    assert not Permission.objects.filter(codename="queue_access_temp-a").exists()


@pytest.mark.xfail(strict=True, raises=IntegrityError,
                   reason="F-04b: recriar fila com o mesmo slug depois do delete em lote estoura IntegrityError (HTTP 500)")
def test_recriar_fila_com_mesmo_slug_apos_delete_em_lote():
    q = Queue.objects.create(title="Temporaria", slug="temp-b")
    Queue.objects.filter(pk=q.pk).delete()
    Queue.objects.create(title="Temporaria nova", slug="temp-b")


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="F-07: GET /api/tickets/ avalia a tabela inteira e consulta custom fields ticket a ticket (N+1 antes da paginação)")
def test_listagem_da_api_respeita_orcamento_de_queries():
    fila = Queue.objects.create(title="Pico", slug="pico", allow_public_submission=True)
    Ticket.objects.bulk_create([Ticket(title=f"t{i}", queue=fila, submitter_email="a@x.invalid") for i in range(150)])
    admin = User.objects.create_user("adm", password="x", is_staff=True, is_superuser=True)
    c = APIClient(); c.force_authenticate(admin)
    with CaptureQueriesContext(connection) as ctx:
        resp = c.get("/api/tickets/?page_size=5")
    assert resp.status_code == 200 and len(resp.json()["results"]) == 5
    assert len(ctx) <= 15, f"{len(ctx)} queries para uma página de 5 tickets (150 no banco)"


# --------------------------------------------------------------------------------------
# O QUE RESISTIU (regressão): isolamento entre filas e vazamento
# --------------------------------------------------------------------------------------
def test_atendente_de_varejo_nao_ve_ticket_de_ouvidoria_nem_banco(client, cenario):
    _, u, t = cenario
    client.force_login(u["varejo"])
    for alheio in ("ouvidoria", "banco"):
        r = client.get(reverse("helpdesk:view", args=[t[alheio].id]))
        assert f"SIGILO-{alheio.upper()}" not in r.content.decode("utf-8", "ignore")
        assert CPF_SINTETICO not in r.content.decode("utf-8", "ignore")
    r = client.get(reverse("helpdesk:view", args=[t["varejo"].id]))
    assert r.status_code == 200 and "SIGILO-VAREJO" in r.content.decode()


def test_api_so_lista_tickets_das_filas_do_atendente(cenario):
    _, u, t = cenario
    c = APIClient(); c.force_authenticate(u["varejo"])
    corpo = c.get("/api/tickets/").json()
    assert {x["title"] for x in corpo["results"]} == {"SIGILO-VAREJO"}


def test_api_nao_devolve_detalhe_de_ticket_alheio(cenario):
    _, u, t = cenario
    c = APIClient(); c.force_authenticate(u["varejo"])
    assert c.get(f"/api/tickets/{t['ouvidoria'].id}/").status_code == 404


def test_api_nao_deixa_criar_ticket_em_fila_alheia(cenario):
    q, u, _ = cenario
    c = APIClient(); c.force_authenticate(u["varejo"])
    r = c.post("/api/tickets/", {"queue": q["ouvidoria"].id, "title": "invasao", "submitter_email": "a@x.invalid"},
               format="json")
    assert r.status_code == 400 and not Ticket.objects.filter(title="invasao").exists()


def test_api_nao_deixa_responder_ticket_alheio(cenario):
    _, u, t = cenario
    c = APIClient(); c.force_authenticate(u["varejo"])
    r = c.post("/api/followups/", {"ticket": t["banco"].id, "title": "x", "comment": "x", "public": True},
               format="json")
    assert r.status_code == 400 and not FollowUp.objects.filter(ticket=t["banco"]).exists()


def test_relatorios_so_somam_filas_acessiveis(client, cenario):
    _, u, _ = cenario
    client.force_login(u["varejo"])
    r = client.get(reverse("helpdesk:report_index"))
    assert r.status_code == 200
    html = r.content.decode("utf-8", "ignore")
    assert "Ouvidoria" not in html and "Banco Transacional" not in html


def test_formulario_publico_recusa_fila_privada(client, cenario):
    q, _, _ = cenario
    client.post(reverse("helpdesk:home"), {"queue": q["banco"].id, "title": "fura-fila", "body": "x",
                                           "priority": 3, "submitter_email": "c@x.invalid"})
    assert not Ticket.objects.filter(title="fura-fila").exists()


def test_nota_interna_com_cpf_nao_vai_por_email_ao_cliente(cenario):
    """LGPD: nota privada (public=False) não pode chegar ao e-mail do solicitante.
    Inclui controle positivo: a resposta PÚBLICA chega ao cliente (prova que o caminho de e-mail está ativo)."""
    call_command("loaddata", "emailtemplate.json", verbosity=0)
    q, u, t = cenario
    mail.outbox.clear()
    update_ticket(u["varejo"], t["varejo"], comment="Resposta publica de controle ABC123", public=True)
    ao_cliente = [m for m in mail.outbox if "varejo@x.invalid" in m.to]
    assert any("ABC123" in m.body for m in ao_cliente), "controle: a resposta pública deveria chegar ao cliente"

    mail.outbox.clear()
    update_ticket(u["varejo"], t["varejo"], comment=f"Titular confirmou CPF {CPF_SINTETICO}. NAO COMPARTILHAR.",
                  public=False)
    ao_cliente = [m for m in mail.outbox if "varejo@x.invalid" in m.to]
    assert all(CPF_SINTETICO not in m.body for m in ao_cliente)
    assert all(CPF_SINTETICO not in (m.alternatives[0][0] if m.alternatives else "") for m in ao_cliente)
