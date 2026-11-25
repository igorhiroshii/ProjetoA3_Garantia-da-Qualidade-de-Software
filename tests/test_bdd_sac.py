import json
import sys
from datetime import date, timedelta
from pathlib import Path

from pytest_bdd import given, parsers, scenarios, then, when

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sac_omnichannel.cdc import avaliar_arrependimento  # noqa: E402
from triage.triage import LLMTriager  # noqa: E402

scenarios("features/sac.feature")
HOJE = date(2026, 11, 24)


@given(parsers.parse("uma compra recebida há {dias:d} dias"), target_fixture="ctx")
def _compra(dias):
    return {"recebimento": HOJE - timedelta(days=dias)}


@when("o cliente pede o cancelamento por arrependimento")
def _pede(ctx):
    ctx["res"] = avaliar_arrependimento(ctx["recebimento"], HOJE)


@then("o pedido é aceito")
def _aceito(ctx):
    assert ctx["res"].pode


@then("o pedido é recusado")
def _recusado(ctx):
    assert not ctx["res"].pode


@then(parsers.parse("restam {n:d} dias de prazo"))
def _restam(ctx, n):
    assert ctx["res"].dias_restantes == n


@given(parsers.parse('um chamado na fila "{fila}" com o texto "{texto}"'), target_fixture="ctx")
def _chamado(fila, texto):
    return {"fila": fila, "texto": texto}


@when(parsers.parse('a triagem roda com um modelo que responde "{urgencia}"'))
def _triagem(ctx, urgencia):
    modelo = lambda prompt: json.dumps({"urgencia": urgencia, "categoria": "outro", "justificativa": "roteiro"})  # noqa: E731
    ctx["r"] = LLMTriager(modelo).classify(ctx["texto"], ctx["fila"])


@then(parsers.parse('a urgência final é "{esperada}"'))
def _urg(ctx, esperada):
    assert ctx["r"].urgencia == esperada


@then("o chamado vai para revisão humana")
def _rev(ctx):
    assert ctx["r"].revisao_humana


@then("o chamado é marcado como suspeita de injeção")
def _inj(ctx):
    assert ctx["r"].suspeita_injecao
