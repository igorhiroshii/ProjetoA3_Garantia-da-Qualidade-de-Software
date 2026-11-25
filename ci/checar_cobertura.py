"""Catraca de cobertura de ramo por arquivo crítico (lê o JSON do coverage.py).

Uso:  coverage json -o cov.json && python ci/checar_cobertura.py cov.json ci/cobertura_minima.json
O piso de cada arquivo é o valor medido na linha de base. Subir o piso é livre; baixar exige justificar no PR.
"""
import json
import sys


def main(cov_json, minimos_json):
    cov = json.load(open(cov_json, encoding="utf-8"))["files"]
    minimos = json.load(open(minimos_json, encoding="utf-8"))
    falhas = []
    for sufixo, piso in minimos.items():
        achados = [v for k, v in cov.items() if k.endswith(sufixo)]
        if not achados:
            falhas.append(f"{sufixo}: arquivo ausente do relatório")
            continue
        s = achados[0]["summary"]
        ramos = s["covered_branches"] / s["num_branches"] if s["num_branches"] else 1.0
        marca = "ok " if ramos + 1e-9 >= piso else "BAIXOU"
        print(f"{marca} {sufixo:55} ramos {ramos:6.1%} (piso {piso:.1%})")
        if ramos + 1e-9 < piso:
            falhas.append(f"{sufixo}: {ramos:.1%} abaixo de {piso:.1%}")
    print("GATE DE COBERTURA:", "REPROVADO" if falhas else "APROVADO")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
