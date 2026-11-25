# sac_qa_kit

Auditoria de qualidade do **Django-Helpdesk 2.6.2** em um SAC omnichannel fictício (varejo, telecom e energia, bancos).
Projeto A3 de Gestão e Qualidade de Software 2026/2, caminho "sistema existente". Leia primeiro o `RELATORIO.md`.

## O que tem aqui
| Pasta | Conteúdo |
| --- | --- |
| `seed/` | ambiente fictício: 7 filas, usuários, casos de borda, picos (`seed_sac_omnichannel.py`) |
| `sac_omnichannel/` | extensão nossa: prazo de arrependimento do CDC (feita em TDD) |
| `triage/` | triagem de urgência com guardrails, conjunto de ouro, métricas e avaliação |
| `tests/` | testes de defeito (`xfail` estrito), propriedades, fuzz, BDD em português |
| `ci/` | workflow do quality gate, catracas, hook de commit |
| `results/` | saídas do mutmut, cobertura base e avaliação da triagem |

## Como rodar
```bash
pip install pytest pytest-cov pytest-bdd hypothesis ruff bandit mutmut==3.8.1
python -m pytest tests/test_a3_triage.py tests/test_a3_triage_mutantes.py tests/test_cdc_arrependimento.py tests/test_bdd_sac.py
python -m triage.rodar_avaliacao --gate --conhecidas ci/gate_conhecido.json
# testes com banco: precisam de um clone do django-helpdesk ao lado (veja RELATORIO.md, seção 8)
```

## Como contribuir
1. Branch curta a partir da `main` (`feat/...`, `fix/...`), no máximo 2 dias de vida.
2. Commits no padrão Conventional Commits (`cp ci/hooks/commit-msg .git/hooks/commit-msg`).
3. Pull request com o modelo de `.github/pull_request_template.md`; o check `quality-gate` precisa estar verde.
4. Corrigiu um defeito conhecido? Remova o `xfail` do teste dele, senão o build quebra de propósito.

## Versionamento
SemVer em tags `vMAJOR.MINOR.PATCH`; o histórico de mudanças está em `CHANGELOG.md`.

## Limites
Sem LLM real, sem execução do workflow no GitHub, rótulos de ouro de uma pessoa só. Detalhes no `RELATORIO.md`.
Teste do quality gate.
