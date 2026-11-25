## O que muda e por quê
<!-- uma frase, ligada a uma SM ou defeito (ex.: SM-01, F-02) -->

## Como foi testado
- [ ] teste novo ou ajustado (red antes, green depois)
- [ ] `ruff check .` e `bandit -r sac_omnichannel triage seed -ll` limpos
- [ ] se tocou em triagem: `python -m triage.rodar_avaliacao --gate --conhecidas ci/gate_conhecido.json`
- [ ] se corrigiu um defeito: removi o `xfail` do teste correspondente

## Risco e rollback
<!-- fila ou dado afetado; como voltar -->
