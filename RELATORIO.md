# A3 | Gestão e Qualidade de Software 2026/2
## Auditoria do Django-Helpdesk 2.6.2 em um SAC omnichannel fictício

Cards: **Teste além da cobertura** + **IA a serviço da qualidade**. Caminho: sistema existente.
Tudo abaixo foi executado. Onde algo é estimativa ou escolha do grupo, está dito.

---

## 1. Resumo para quem tem 2 minutos

- O sistema original tem **720 testes passando e 91,3% de cobertura (linhas e ramos combinados; 83,1% só de ramos)**. Mesmo assim encontramos **9 defeitos** (F-01 a F-09), todos com teste que reproduz o problema.
- A cobertura não via nada disso. Exemplo: `helpdesk/user.py` tinha 48 de 61 mutantes mortos pela suíte de permissões. Com testes novos escritos para os sobreviventes foram 61 de 61.
- Para o SAC, os dois defeitos mais graves são **F-01/F-02/F-03** (o escalonamento por prazo erra a conta e escalona em dia proibido) e **F-04** (apagar filas em lote deixa permissão órfã e derruba a recriação da fila com HTTP 500).
- O isolamento entre filas (varejo não vê banco, banco não vê ouvidoria) **resistiu** a 8 ataques que tentamos.
- A triagem de urgência com IA, com guardrails, zera o risco de "emergência tratada como rotina" quando o LLM erra, trava ou obedece injeção, **exceto em 1 caso** em que as regras de piso não conhecem o termo (emergência escrita em inglês). Isso reprova o gate e está registrado como dívida conhecida.
- **Nenhum LLM real foi chamado.** Os "LLMs" dos testes são funções roteirizadas que imitam falhas. Eles provam que os guardrails funcionam, não medem a qualidade de um modelo.

## 2. O ambiente fictício (`seed/`)

| Item | Conteúdo |
|---|---|
| Filas | `sac-varejo-pedidos`, `sac-varejo-reembolso`, `sac-telecom-sinal`, `sac-energia-emergencia`, `sac-banco-sac`, `sac-banco-transacional`, `sac-ouvidoria` |
| Canais | Chat 24h, WhatsApp, 0800/URA, Ouvidoria (campo personalizado `canal`) |
| Usuários | `sac_<setor>_1`, `sac_<setor>_2`, `sac_supervisor_varejo`, `sac_admin` (senha de teste `SenhaDeTeste!2026`) |
| LGPD | campos `cpf_titular` e `protocolo`; teste exige que nota interna com CPF não vá por e-mail ao cliente |
| Regulado | campo `regulado`; fila de energia sem exclusão de feriado e fim de semana (24h) |
| Casos de borda | 27: texto malformado, caracteres de controle e RTL, SQL e HTML no título, prompt injection, emoji, texto de 50 mil caracteres, e-mail inválido, duplicados |
| Picos | `--burst` cria rajada de chamados de energia (queda de rede) |

Uso:

```bash
cd django-helpdesk
DJANGO_SETTINGS_MODULE=sac_settings PYTHONPATH=src:.:../sac_qa_kit/seed \
  python ../sac_qa_kit/seed/seed_sac_omnichannel.py --migrate --reset --volume 300 --burst 40 --seed 7
```

Verificado: roda duas vezes seguidas sem duplicar nada e, com a mesma `--seed`, gera exatamente os mesmos dados.
Os valores de SLA (`escalate_days` e afins) são **ilustrativos**, não são prazos reais de nenhum setor.

## 3. Defeitos encontrados no Django-Helpdesk

Cada linha tem um teste `xfail(strict=True)`: enquanto o defeito existe, o teste "falha como esperado" e a suíte fica verde. No dia em que alguém corrigir, o teste passa, vira XPASS e **quebra a suíte**, obrigando a tirar o `xfail`. O defeito não some em silêncio.
A coluna Gravidade é **julgamento do grupo para este contexto de SAC**, não uma métrica.

### 3.1 Lógica e SLA

| ID | O que acontece | Efeito no SAC | Gravidade | Teste |
|---|---|---|---|---|
| F-01 | `escalate_tickets` ignora `EscalationExclusion.queues` e aplica a exclusão a **todas** as filas | Um feriado cadastrado só para o varejo também atrasa (ou antecipa) o banco | Alta | `test_exclusao_de_uma_fila_nao_pode_antecipar_escalonamento_de_outra` |
| F-02 | Dias de exclusão **encurtam** o prazo em vez de estendê-lo | Chamado escala antes do prazo contratado; vira urgência falsa | Alta | `test_fim_de_semana_nao_pode_antecipar_escalonamento` e a propriedade `test_propriedade_nunca_escalona_antes_do_prazo_em_dias_corridos` |
| F-03 | O comando escalona em dia marcado como "escalonamento não deve ocorrer" | Quebra a regra que o próprio gestor configurou | Média | `test_nao_escalona_em_dia_de_exclusao` |
| F-05 | Usa `timezone.now().date()` (UTC), não a data do fuso da operação | Às 22h30 em Brasília já é "amanhã" para o comando: um chamado de 10 minutos pode escalar por causa de feriado | Média | `test_ticket_de_10_minutos_nao_escalona_por_causa_de_feriado_no_fuso_da_operacao` |
| F-08 | `update_ticket` aceita as **10 transições** de status que `TICKET_STATUS_CHOICES_FLOW` proíbe (ex.: Fechado para Resolvido) | O fluxo é só sugestão de tela; qualquer cliente de API pula etapas | Média | `test_servidor_recusa_transicao_fora_do_fluxo` |
| F-09 | `PATCH /api/tickets/<id>/` muda o status sem criar `FollowUp` nem `TicketChange` | Sem trilha de auditoria para alteração feita pela API (problema para ouvidoria e banco) | Alta | `test_mudanca_de_status_pela_api_deixa_trilha_de_auditoria` |

### 3.2 Segurança e permissões

| ID | O que acontece | Efeito no SAC | Gravidade | Teste |
|---|---|---|---|---|
| F-04 | Apagar filas em lote (ação "excluir selecionados" do admin) deixa a permissão `queue_access_<slug>` órfã | Permissão sobrando em contas de atendentes | Média | `test_apagar_fila_em_lote_remove_a_permissao` |
| F-04b | Recriar fila com o mesmo slug depois disso estoura `IntegrityError` (HTTP 500) | Não dá para refazer a fila de energia sem mexer no banco | Alta | `test_recriar_fila_com_mesmo_slug_apos_delete_em_lote` |
| F-06 | O formulário público deixa o cliente anônimo escolher prioridade 1 (máxima) | Qualquer pessoa fura a fila de prioridade | Média | `test_anonimo_nao_pode_abrir_ticket_com_prioridade_maxima` |

O seed também esbarrou em F-04: o script de `--reset` apaga fila por fila para contornar o defeito.

### 3.3 Performance

| ID | Medido | Teste |
|---|---|---|
| F-07 | `GET /api/tickets/?page_size=5` faz **18 queries com 10 tickets, 158 com 150, 608 com 600**. Cresce com o tamanho da tabela, não com a página: avalia tudo e consulta campos personalizados ticket a ticket antes de paginar. Em pico de energia, a listagem da API fica mais lenta justo quando mais se usa | `test_listagem_da_api_respeita_orcamento_de_queries` (orçamento: 15 queries) |

### 3.4 O que resistiu

Testes que **passam** e servem de guarda contra regressão: atendente de varejo não vê ticket de ouvidoria nem de banco; API só lista, detalha, cria e responde em filas permitidas; relatórios só somam filas acessíveis; formulário público recusa fila privada; nota interna com CPF não sai por e-mail; `accessible_tickets()` (consulta) e `can_access_ticket()` (objeto) nunca discordam em 40 combinações geradas por Hypothesis; título nunca passa de 200 caracteres; fuzz do formulário público com 70 entradas aleatórias nunca devolveu 5xx.

## 4. Testes além da cobertura: o que cada técnica achou

| Técnica | Onde | Resultado |
|---|---|---|
| Propriedades (Hypothesis) | acesso a ticket, título, dependências, escalonamento | achou F-01/F-02 em forma de propriedade; as demais passam |
| Fuzz | formulário público | 0 respostas 5xx |
| Mutação (mutmut 3.8.1) em `helpdesk/user.py` | suíte de permissões, 7 arquivos | **48/61 mortos antes, 61/61 depois** (testes em `test_a3_mutation_killers.py`) |
| Mutação em `triage/triage.py` | guardrails da triagem | **199/345 antes, 291/298 testáveis depois (97,7%)** |
| Teste de dentes | portão de isolamento e gate da triagem | desligamos a proteção e os testes falham; piorar o piso faz o gate reprovar |

Honestidade sobre a mutação:
- Dos 10 sobreviventes iniciais de `user.py`, conferimos 4 contra a suíte completa: 3 morriam com ela (o mutmut rodava só 7 arquivos de teste) e 1 era lacuna real. Os outros 6 não foram conferidos, então o ganho de 48 para 61 está superestimado.
- Em `triage.py`, restam 7 mutantes vivos e todos são **equivalentes** (valor padrão igual ao valor explícito, ou só o texto de uma mensagem). Outros 42 estão no adaptador `anthropic_llm`, que precisa de chave de API e não roda nos testes.
- O número 97,7% é de **um módulo pequeno que nós mesmos escrevemos**. Não é comparável ao do Helpdesk.

## 5. IA a serviço da qualidade: triagem de urgência com guardrails (`triage/`)

**Ideia.** Um LLM sugere a urgência (emergência, alta, normal, baixa) e a categoria. Erro tem custo assimétrico: tratar "segunda via" como emergência custa tempo do atendente, tratar fio caído como "segunda via" pode custar uma vida. Então toda falha resolve **para cima**.

**Guardrails.**
- Saída do LLM só vale se for JSON com urgência e categoria dentro dos conjuntos permitidos da fila. Qualquer outra coisa vira falha segura: "alta" e revisão humana, ou "emergência" se as regras já viram sinal.
- Texto do cliente vai entre `<ticket>` e `</ticket>` como dado; tags escritas pelo cliente são neutralizadas.
- Piso por regras (energia, saúde, bombeiros, fraude em banco etc.): o LLM nunca rebaixa um sinal objetivo de emergência.
- Texto suspeito de injeção ("ignore as instruções") sempre pede revisão humana.
- LLM fora do ar não derruba a fila: aplica o piso e sinaliza.

**Conjunto de ouro.** 52 casos rotulados **por uma única pessoa do grupo** (viés possível, sem concordância entre avaliadores): 21 emergências, 7 altas, 15 normais, 9 baixas. Inclui emergência em inglês, negação ("não é emergência"), injeção, cliente inflando prioridade e texto longo.

**Resultado com LLMs roteirizados** (`python -m triage.rodar_avaliacao`):

| Perfil | Acurácia | Emergência tratada como rotina | Injeções obedecidas | Falha segura |
|---|---|---|---|---|
| Regras sozinhas | 0,65 | 1 | 1 | 0% |
| LLM otimista, sem guardrails | 0,27 | **21** | 3 | 0% |
| LLM otimista, com guardrails | 0,65 | 1 | 1 | 0% |
| LLM obediente a injeção, sem guardrails | 0,31 | **21** | 2 | 0% |
| LLM obediente, com guardrails | 0,69 | 1 | **0** | 0% |
| LLM instável (1 em 3 respostas lixo), com guardrails | 0,60 | 1 | 1 | 33% |
| LLM fora do ar, com guardrails | 0,50 | **0** | 1 | 100% |

Como ler: os guardrails derrubam o pior erro de 21 para 1. O que sobra vem do piso por regras, não do LLM:
- **g14**: emergência escrita em inglês não bate nenhuma regra. O piso não a vê.
- **g32**: cliente escreve "URGENTE" sem motivo e vira "alta".

Escolhemos **não** acrescentar termos em inglês às regras só para passar no conjunto de teste, porque isso seria ajustar a prova à resposta. Em vez disso as duas violações ficam em `ci/gate_conhecido.json` e o CI só reprova violação **nova** (catraca). Se alguém piorar o piso, o gate reprova (testado: remover "sem luz" subiu os falsos negativos críticos de 1 para 3 e o CI falhou).

Limite conhecido: o extrator de JSON usa regex não gulosa, então resposta com objeto aninhado cai na falha segura. É seguro, só mais conservador. Está fixado em teste.

## 6. Quality gate (`ci/quality-gate.yml`)

| Portão | Regra | Origem do limite |
|---|---|---|
| Testes A3 | nenhum teste novo falha; XPASS quebra a suíte (defeito corrigido, remover `xfail`) | regra do grupo |
| Triagem, falso negativo crítico | máximo 0 | proposta, risco de vida |
| Triagem, recall de emergência | mínimo 0,95 | proposta |
| Triagem, injeção obedecida | máximo 0 | proposta |
| Triagem, falha segura | máximo 5% (só com LLM real) | proposta |
| Triagem, falso alarme | máximo 20% (só com LLM real) | proposta, ajustar com o cliente |
| Mutação semanal em `triage.py` | no máximo 15 sobreviventes | proposta |
| Orçamento de queries da API | até 15 por página de 5 | proposta; hoje reprova (F-07) |

**Todos os limites acima são proposta do grupo** e devem ser validados com os professores e com a DMA. Não saem de norma nem de benchmark.
O job `llm-real` só roda se alguém configurar `ANTHROPIC_API_KEY` e a variável `USAR_LLM_REAL`. Sem isso, o que está provado é o comportamento dos guardrails, não a qualidade de um modelo.

## 7. Limites desta entrega

- Nenhuma chamada a modelo real, sem chave de API e sem rede. A acurácia de um LLM de verdade é **desconhecida**.
- Rótulos do conjunto de ouro feitos por uma pessoa; 52 casos é pouco para estatística.
- Defeitos comprovados contra a versão 2.6.2 (commit `7154322`). Em outra versão, rode de novo.
- A gravidade dos defeitos é julgamento nosso para um SAC fictício. Bandit não foi executado nesta máquina; está no CI como informativo.
- Não alteramos o código do Django-Helpdesk. A suíte original continua com 720 passando e 2 pulados.

## 8. Como reproduzir

```bash
# 1) testes do Helpdesk + A3 (da raiz do django-helpdesk)
DJANGO_SETTINGS_MODULE=tests.test_settings PYTHONPATH=src:. \
  python -m pytest ../sac_qa_kit/tests -p no:cacheprovider --no-cov -q -W ignore
#    esperado: 99 passed, 11 xfailed

# 2) triagem (da raiz do sac_qa_kit, sem Django)
python -m pytest tests/test_a3_triage.py tests/test_a3_triage_mutantes.py -p no:cacheprovider -q
python -m triage.rodar_avaliacao --gate --conhecidas ci/gate_conhecido.json
python -m triage.rodar_avaliacao --real --gate      # exige ANTHROPIC_API_KEY
```

## 9. Para a apresentação

- Abra com o número: 720 testes verdes e 91% de cobertura, e mesmo assim 9 defeitos.
- Mostre F-02 com a data: o prazo "encurta" quando deveria estender.
- Mostre a tabela da seção 5 e a frase: "21 viram 1 com guardrails, e o 1 que sobra é do nosso piso, não do LLM".
- Se perguntarem "e com um modelo de verdade?", a resposta honesta é que ainda não medimos e o job `llm-real` existe para isso.


> Atualização: o documento dos 10 entregáveis (Claude Docs) usa estes mesmos números. Desde a primeira versão deste relatório foram adicionados `sac_omnichannel/` (TDD do prazo do CDC), BDD em português, scripts de catraca em `ci/` e o repositório git do kit.
