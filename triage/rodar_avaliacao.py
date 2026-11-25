"""
Avalia a triagem contra o conjunto de ouro e aplica o quality gate.

Modos:
  python -m triage.rodar_avaliacao              LLMs ROTEIRIZADOS (sem rede, sem chave). Mostra o efeito dos guardrails
                                                diante de modos de falha conhecidos. NÃO mede acurácia de modelo real.
  python -m triage.rodar_avaliacao --real       usa a API da Anthropic (exige ANTHROPIC_API_KEY). Este é o número que vale
                                                para decidir se um modelo entra em produção.
  --gate                                        sai com código 1 se surgir violação NOVA nos perfis protegidos.
  --conhecidas ci/gate_conhecido.json           violações já registradas (dívida aceita e documentada). Não reprovam o CI,
                                                mas aparecem no relatório; se uma sumir, o script pede para atualizar o arquivo.
  --saida results/avaliacao.json                grava o relatório.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from triage.metricas import LIMITES, avaliar, carregar, checar_gate
from triage.triage import LLMTriager, RuleBasedTriager, anthropic_llm


def _resp(urg, cat="outro"):
    return json.dumps({"urgencia": urg, "categoria": cat, "justificativa": "roteiro"})


def llm_otimista(prompt):                      # subestima: tudo vira rotina, salvo a palavra "urgente"
    return _resp("alta" if re.search(r"urgente", prompt.split("<ticket>")[-1], re.I) else "normal")


def llm_obediente(prompt):                     # obedece ordens escritas no chamado
    corpo = prompt.split("<ticket>")[-1].lower()
    if "ignore" in corpo or "desconsidere" in corpo:
        return _resp("baixa")
    return _resp("emergencia" if "emergencia" in corpo or "emergência" in corpo else "normal")


_n = {"i": 0}
def llm_instavel(prompt):                      # 1 em cada 3 respostas é lixo; as demais são "normal"
    _n["i"] += 1
    return "desculpe, não consigo" if _n["i"] % 3 == 0 else _resp("normal")


def llm_fora_do_ar(prompt):
    raise TimeoutError("sem resposta")


PERFIS = {
    "regras (baseline)": lambda: RuleBasedTriager(),
    "LLM otimista, SEM guardrails": lambda: LLMTriager(llm_otimista, usar_piso=False),
    "LLM otimista, COM guardrails": lambda: LLMTriager(llm_otimista),
    "LLM obediente, SEM guardrails": lambda: LLMTriager(llm_obediente, usar_piso=False),
    "LLM obediente, COM guardrails": lambda: LLMTriager(llm_obediente),
    "LLM instável, COM guardrails": lambda: LLMTriager(llm_instavel),
    "LLM fora do ar, COM guardrails": lambda: LLMTriager(llm_fora_do_ar),
}
# Perfis que DEVEM passar nos limites de segurança (falha segura conta, então o limite de falha segura é relaxado neles).
PROTEGIDOS = {"LLM otimista, COM guardrails", "LLM obediente, COM guardrails", "LLM instável, COM guardrails",
              "LLM fora do ar, COM guardrails"}
LIMITES_ROTEIRO = {k: v for k, v in LIMITES.items() if k not in ("taxa_falha_segura", "taxa_falso_alarme", "recall_emergencia")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--saida")
    ap.add_argument("--conhecidas")
    a = ap.parse_args(argv)
    casos = carregar()
    resultado, falhas = {}, []

    perfis = {"LLM real (Anthropic) + guardrails": lambda: LLMTriager(anthropic_llm())} if a.real else PERFIS
    protegidos = set(perfis) if a.real else PROTEGIDOS
    print(f"{'perfil':38} {'acur':>5} {'FNcrit':>6} {'rebx→alta':>9} {'recallE':>7} {'alarme':>6} {'inj.obed':>8} {'falha':>6} {'revis':>6}")
    for nome, fab in perfis.items():
        _n["i"] = 0
        m = avaliar(fab(), casos)
        resultado[nome] = m
        f = lambda v: "  -  " if v is None else f"{v:5.2f}"
        print(f"{nome:38} {f(m['acuracia'])} {m['falso_negativo_critico']:6d} {m['emergencias_rebaixadas_a_alta']:9d} "
              f"{f(m['recall_emergencia']):>7} {m['falsos_alarmes']:6d} {m['injecoes_obedecidas']:8d} "
              f"{f(m['taxa_falha_segura']):>6} {f(m['taxa_revisao_humana']):>6}")
        if nome in protegidos:
            lim = LIMITES if a.real else LIMITES_ROTEIRO
            for v in checar_gate(m, lim):
                falhas.append(f"{nome}: {v}")
    conhecidas = set(json.loads(Path(a.conhecidas).read_text(encoding="utf-8"))) if a.conhecidas else set()
    novas = [v for v in falhas if v not in conhecidas]
    resolvidas = sorted(conhecidas - set(falhas))
    print("\nGATE:", "APROVADO" if not novas else "REPROVADO", f"({len(falhas)} violações, {len(falhas) - len(novas)} já conhecidas)")
    for v in falhas:
        print("  -" if v in novas else "  · conhecida:", v)
    for v in resolvidas:
        print("  ✔ resolvida, remova de gate_conhecido.json:", v)
    if a.saida:
        Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
        slim = {k: {kk: vv for kk, vv in m.items() if kk != "erros"} | {"erros": m["erros"]} for k, m in resultado.items()}
        Path(a.saida).write_text(json.dumps({"modo": "real" if a.real else "roteirizado", "gate_violacoes": falhas, "gate_novas": novas, "perfis": slim},
                                            ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if (a.gate and novas) else 0


if __name__ == "__main__":
    sys.exit(main())
