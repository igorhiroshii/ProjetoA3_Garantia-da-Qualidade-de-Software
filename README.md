# sac_qa_kit

Kit do A3 (Gestão e Qualidade de Software 2026/2). Leia primeiro o **RELATORIO.md**.

- `seed/` ambiente fictício de SAC omnichannel (Django-Helpdesk 2.6.2)
- `tests/` testes de defeito (xfail estrito), guarda, propriedades, fuzz e matadores de mutantes
- `triage/` triagem de urgência com guardrails, conjunto de ouro, métricas e avaliação
- `ci/` workflow do quality gate e violações conhecidas
- `results/` saídas do mutmut, cobertura base e avaliação da triagem

Requisitos: Python 3.12, `pytest pytest-django hypothesis freezegun mutmut==3.8.1`, clone do django-helpdesk ao lado.
