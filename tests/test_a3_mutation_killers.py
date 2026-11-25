"""
A3 | Teste além da cobertura | Testes escritos para MATAR os mutantes de `helpdesk/user.py` que
sobreviveram à suíte de permissões (mutmut 3.8.1, 7 arquivos de teste, 61 mutantes, 13 não mortos).

Cada teste diz qual mutante ele mata. Nome do mutante = <função>__mutmut_<n> no relatório do mutmut.

Rodar (da raiz do django-helpdesk):
    DJANGO_SETTINGS_MODULE=tests.test_settings PYTHONPATH=src:. pytest ../sac_qa_kit/tests/test_a3_mutation_killers.py
"""
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission

from helpdesk import settings as hd
from helpdesk.models import KBCategory, KBItem, Queue, Ticket
from helpdesk.user import HelpdeskUser

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def filas(db):
    return (Queue.objects.create(title="Pub", slug="pub", allow_public_submission=True),
            Queue.objects.create(title="Priv", slug="priv", allow_public_submission=False),
            Queue.objects.create(title="Liberada", slug="liberada", allow_public_submission=False))


def _staff(nome, *filas_liberadas, **kw):
    u = User.objects.create_user(nome, password="x", is_staff=True, **kw)
    for f in filas_liberadas:
        u.user_permissions.add(Permission.objects.get(codename=f"queue_access_{f.slug}"))
    return User.objects.get(pk=u.pk)         # recarrega: sem cache de permissões


# ---------------------------------- get_queues ----------------------------------------
def test_mata_get_queues_4_usuario_restrito_ve_filas_publicas_mais_as_liberadas(filas, monkeypatch):
    """get_queues__mutmut_4: allow_public_submission=True -> None. Sem este teste, o produto deixava de
    listar filas públicas nos seletores e nenhum teste percebia."""
    monkeypatch.setattr(hd, "HELPDESK_ENABLE_PER_QUEUE_STAFF_PERMISSION", True)
    pub, priv, liberada = filas
    ids = set(HelpdeskUser(_staff("a", liberada)).get_queues().values_list("slug", flat=True))
    assert ids == {"pub", "liberada"}            # pública entra; privada sem permissão NÃO entra


def test_mata_get_queues_7_sem_isolamento_ativo_staff_ve_todas_as_filas(filas, monkeypatch):
    """get_queues__mutmut_7: 'and' -> 'or'. Com o isolamento DESLIGADO, todo staff vê todas as filas."""
    monkeypatch.setattr(hd, "HELPDESK_ENABLE_PER_QUEUE_STAFF_PERMISSION", False)
    assert HelpdeskUser(_staff("b")).get_queues().count() == 3


def test_get_queues_superuser_ve_todas_mesmo_com_isolamento_ativo(filas, monkeypatch):
    monkeypatch.setattr(hd, "HELPDESK_ENABLE_PER_QUEUE_STAFF_PERMISSION", True)
    assert HelpdeskUser(_staff("c", is_superuser=True)).get_queues().count() == 3


# -------------------------------- can_edit_followup -----------------------------------
def test_mata_can_edit_followup_4_followup_sem_autor_nunca_e_editavel(monkeypatch):
    """can_edit_followup__mutmut_4: 'return False' -> 'return True' na checagem de autoria."""
    monkeypatch.setattr(hd, "HELPDESK_SHOW_EDIT_BUTTON_FOLLOW_UP", True)
    sem_autor = SimpleNamespace(user=None)
    assert HelpdeskUser(_staff("d", is_superuser=True)).can_edit_followup(sem_autor) is False


def test_can_edit_followup_autor_e_superuser_sim_outro_staff_nao(monkeypatch):
    monkeypatch.setattr(hd, "HELPDESK_SHOW_EDIT_BUTTON_FOLLOW_UP", True)
    autor, outro, root = _staff("autor"), _staff("outro"), _staff("root", is_superuser=True)
    f = SimpleNamespace(user=autor)
    assert HelpdeskUser(autor).can_edit_followup(f) is True
    assert HelpdeskUser(root).can_edit_followup(f) is True
    assert HelpdeskUser(outro).can_edit_followup(f) is False


def test_can_edit_followup_botao_desligado_ninguem_edita(monkeypatch):
    monkeypatch.setattr(hd, "HELPDESK_SHOW_EDIT_BUTTON_FOLLOW_UP", False)
    autor = _staff("autor2", is_superuser=True)
    assert HelpdeskUser(autor).can_edit_followup(SimpleNamespace(user=autor)) is False


# --------------------------- categorias da base de conhecimento -----------------------
@pytest.fixture
def categorias(filas):
    pub, priv, liberada = filas
    mk = lambda slug, **kw: KBCategory.objects.create(name=slug, title=slug, slug=slug, description="d", **kw)
    return {"aberta": mk("aberta", public=True), "da_liberada": mk("da-liberada", public=False, queue=liberada),
            "da_privada": mk("da-privada", public=False, queue=priv), "sem_fila": mk("sem-fila", public=False)}


def test_mata_kbcategory_1_3_4_regras_de_acesso(categorias, filas, monkeypatch):
    """can_access_kbcategory__mutmut_1/3/4: negação de 'public', 'and'->'or' e queue trocada por None."""
    monkeypatch.setattr(hd, "HELPDESK_ENABLE_PER_QUEUE_STAFF_PERMISSION", True)
    h = HelpdeskUser(_staff("e", filas[2]))                       # só a fila "liberada"
    assert h.can_access_kbcategory(categorias["aberta"])
    assert h.can_access_kbcategory(categorias["da_liberada"])               # mata _4 (None)
    assert not h.can_access_kbcategory(categorias["da_privada"])
    assert not h.can_access_kbcategory(categorias["sem_fila"])              # mata _3 (a função devolve None, que é falso)


def test_mata_get_allowed_kb_categories_1_2_3(categorias, filas, monkeypatch):
    monkeypatch.setattr(hd, "HELPDESK_ENABLE_PER_QUEUE_STAFF_PERMISSION", True)
    nomes = {c.slug for c in HelpdeskUser(_staff("f", filas[2])).get_allowed_kb_categories()}
    assert nomes == {"aberta", "da-liberada"}
    assert {c.slug for c in HelpdeskUser(_staff("g", is_superuser=True)).get_allowed_kb_categories()} == {
        "aberta", "da-liberada", "da-privada", "sem-fila"}


# -------------------------------- itens de KB por equipe -------------------------------
def test_mata_get_assigned_kb_items_1_a_4(categorias, monkeypatch):
    """get_assigned_kb_items__mutmut_1..4: o seletor de equipe é injetável (HELPDESK_KBITEM_TEAM_GETTER)."""
    cat = categorias["aberta"]
    mk = lambda t: KBItem.objects.create(category=cat, title=t, question="q", answer="a")
    meu, alheio, sem_equipe = mk("meu"), mk("alheio"), mk("sem-equipe")
    user = _staff("h")

    class Equipe:
        def __init__(self, membros): self.membros = membros
        def is_member(self, u): return u in self.membros

    equipes = {meu.pk: Equipe([user]), alheio.pk: Equipe([]), sem_equipe.pk: None}
    monkeypatch.setattr(hd, "HELPDESK_KBITEM_TEAM_GETTER", lambda item: equipes[item.pk])
    assert {i.title for i in HelpdeskUser(user).get_assigned_kb_items()} == {"meu"}


# ----------------------------- sanidade do próprio helper -----------------------------
def test_anonimo_nao_acessa_ticket_de_ninguem(filas, monkeypatch):
    monkeypatch.setattr(hd, "HELPDESK_ENABLE_PER_QUEUE_STAFF_PERMISSION", True)
    t = Ticket.objects.create(title="t", queue=filas[0])
    assert HelpdeskUser(AnonymousUser()).can_access_ticket(t) is False
