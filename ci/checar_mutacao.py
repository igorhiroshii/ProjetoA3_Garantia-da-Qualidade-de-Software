"""Lê `mutmut results` e reprova se sobrar mutante vivo que não esteja na lista de equivalentes.

Uso:  mutmut run && mutmut results --all true | python ci/checar_mutacao.py --equivalentes ci/mutantes_equivalentes.json --minimo 0.95
Equivalente = mutante que não muda o comportamento observável (valor padrão explícito, texto de mensagem).
Cada entrada da lista precisa de uma justificativa; o nome do mutante só vale enquanto o arquivo-fonte não muda.
"""
import argparse
import json
import re
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equivalentes", required=True)
    ap.add_argument("--minimo", type=float, default=0.95)
    ap.add_argument("--entrada", default="-")
    a = ap.parse_args()
    texto = sys.stdin.read() if a.entrada == "-" else open(a.entrada, encoding="utf-8").read()
    vivos = re.findall(r"^\s+(\S+): survived", texto, flags=re.M)
    sem_teste = len(re.findall(r": no tests", texto))
    mortos = len(re.findall(r": killed", texto))
    perdoados = {e["mutante"] for e in json.load(open(a.equivalentes, encoding="utf-8"))}
    novos = [v for v in vivos if v not in perdoados]
    testaveis = len(vivos) + mortos
    score = (testaveis - len(novos) - sum(v in perdoados for v in vivos)) / max(testaveis - sum(v in perdoados for v in vivos), 1)
    print(f"vivos={len(vivos)} equivalentes_aceitos={len(vivos) - len(novos)} novos={len(novos)} sem_teste={sem_teste}")
    for v in novos:
        print("  NOVO SOBREVIVENTE:", v)
    if novos or score < a.minimo:
        print(f"GATE DE MUTAÇÃO: REPROVADO (score {score:.3f}, mínimo {a.minimo})")
        return 1
    print(f"GATE DE MUTAÇÃO: APROVADO (score {score:.3f}, mínimo {a.minimo})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
