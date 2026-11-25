# Changelog
Formato Keep a Changelog; versões seguem SemVer (MAJOR.MINOR.PATCH).

## [0.1.0] - 2026-11-24
### Adicionado
- Ambiente SAC omnichannel fictício (`seed/`), testes de defeito, propriedades e fuzz (`tests/`).
- Triagem de urgência com guardrails, conjunto de ouro e métricas (`triage/`).
- Módulo de prazo de arrependimento do CDC feito em TDD (`sac_omnichannel/cdc.py`).
- Quality gate de CI (`ci/quality-gate.yml`) com catracas de cobertura, mutação e triagem.
### Conhecido
- 9 defeitos no Django-Helpdesk 2.6.2 fixados como `xfail` estrito (F-01 a F-09); ver `RELATORIO.md`.
