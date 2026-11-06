"""Robô de anúncios do @walterribestrafego (Meta Ads → conversas no Direct).

Lê anuncios.json e, para cada anúncio, cria no Gerenciador de Anúncios:
  campanha (Engajamento) → conjunto (conversas no Direct do Instagram) → criativo (um post seu) → anúncio
TUDO É CRIADO PAUSADO. Só começa a gastar quando você roda "ativar" com o nome do anúncio.

Uso:
  python anuncios.py --check                 confere conta de anúncios, Página e Instagram
  python anuncios.py --simular               mostra o que seria criado e o gasto máximo, sem criar nada
  python anuncios.py --criar                 cria (pausados) os anúncios novos de anuncios.json
  python anuncios.py --ativar  --nome NOME   liga o anúncio (passa pela revisão da Meta e começa a gastar)
  python anuncios.py --pausar  [--nome NOME] pausa um anúncio (ou todos, sem --nome)
  python anuncios.py --relatorio             mostra gasto, alcance e conversas (no resumo da execução do GitHub)
"""
import argparse, datetime as dt, json, os, sys
from zoneinfo import ZoneInfo
from meta import call, accounts, ROOT

TZ = ZoneInfo("America/Sao_Paulo")
CONFIG = os.path.join(ROOT, "anuncios.json")
ESTADO = os.path.join(ROOT, "anuncios_estado.json")
POSTS_ESTADO = os.path.join(ROOT, "publicados.json")
RELATORIO = os.path.join(ROOT, "relatorio_anuncios.md")
TETO_DIARIO = 100  # R$ por dia por anúncio: trava de segurança contra erro de digitação
CONVERSA = "onsite_conversion.messaging_conversation_started_7d"


def conta():
    n = os.environ.get("META_AD_ACCOUNT", "").strip().replace("act_", "")
    if not n.isdigit():
        raise SystemExit("Falta o segredo META_AD_ACCOUNT (número da conta de anúncios, só dígitos).")
    return f"act_{n}"


def carregar():
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    est = json.load(open(ESTADO)) if os.path.exists(ESTADO) else {}
    return cfg, est


def salvar(est):
    json.dump(est, open(ESTADO, "w"), indent=2, ensure_ascii=False)


def dias(a):
    i = dt.date.fromisoformat(a["inicio"]); f = dt.date.fromisoformat(a["fim"])
    return (f - i).days + 1


def validar(a):
    nome = a.get("nome", "?")
    for k in ("nome", "orcamento_diario", "inicio", "fim", "local"):
        if k not in a:
            raise SystemExit(f"{nome}: falta o campo '{k}' em anuncios.json")
    if not (a.get("post") or a.get("ig_media_id")):
        raise SystemExit(f"{nome}: diga qual post anunciar ('post' = data e hora do posts.json, ou 'ig_media_id')")
    v = float(a["orcamento_diario"])
    if v <= 0 or v > TETO_DIARIO:
        raise SystemExit(f"{nome}: orçamento diário R$ {v:.2f} fora do limite (até R$ {TETO_DIARIO}/dia). "
                         "Se for de propósito, aumente TETO_DIARIO em anuncios.py.")
    if dias(a) < 1:
        raise SystemExit(f"{nome}: 'fim' é antes de 'inicio'")
    if dt.date.fromisoformat(a["fim"]) < dt.datetime.now(TZ).date():
        raise SystemExit(f"{nome}: a data de fim já passou")


def media_do_post(a):
    if a.get("ig_media_id"):
        return str(a["ig_media_id"])
    pub = json.load(open(POSTS_ESTADO)) if os.path.exists(POSTS_ESTADO) else {}
    mid = (pub.get(a["post"]) or {}).get("instagram")
    if not mid:
        raise SystemExit(f"{a['nome']}: o post '{a['post']}' ainda não foi publicado pelo robô. "
                         "Publique primeiro ou informe 'ig_media_id'.")
    return mid


def publico(a):
    loc = a["local"]
    t = {
        "geo_locations": {
            "custom_locations": [{"latitude": loc["lat"], "longitude": loc["lng"],
                                  "radius": loc.get("raio_km", 25), "distance_unit": "kilometer"}],
            "location_types": ["home", "recent"],
        },
        "age_min": a.get("idade_min", 25),
        "age_max": a.get("idade_max", 65),
        "publisher_platforms": ["instagram"],
        "instagram_positions": ["stream", "story", "reels", "explore"],
        "device_platforms": ["mobile"],
        "targeting_automation": {"advantage_audience": 1 if a.get("publico_automatico") else 0},
    }
    return t


def iso(dia, fim=False):
    d = dt.datetime.fromisoformat(dia).replace(tzinfo=TZ)
    if fim:
        d = d.replace(hour=23, minute=59)
    elif d.date() == dt.datetime.now(TZ).date():
        d = dt.datetime.now(TZ) + dt.timedelta(minutes=15)
    return d.isoformat(timespec="seconds")


def resumo(a):
    total = float(a["orcamento_diario"]) * dias(a)
    return (f"{a['nome']}: R$ {float(a['orcamento_diario']):.2f}/dia × {dias(a)} dia(s) = até R$ {total:.2f} · "
            f"{a['inicio']} a {a['fim']} · raio {a['local'].get('raio_km', 25)} km de {a['local'].get('nome', 'ponto escolhido')} · "
            f"{a.get('idade_min', 25)}–{a.get('idade_max', 65)} anos · post {a.get('post') or a.get('ig_media_id')}")


def criar(a, page_id, ig_id, act, est):
    mid = media_do_post(a)
    reg = est.setdefault(a["nome"], {})
    if not reg.get("campanha"):
        reg["campanha"] = call("POST", f"{act}/campaigns", name=f"[Robô] {a['nome']}", objective="OUTCOME_ENGAGEMENT",
                               special_ad_categories=[], status="PAUSED",
                               is_adset_budget_sharing_enabled="false")["id"]
        salvar(est)
    if not reg.get("conjunto"):
        reg["conjunto"] = call("POST", f"{act}/adsets", name=f"[Robô] {a['nome']} · Direct",
                               campaign_id=reg["campanha"], billing_event="IMPRESSIONS",
                               optimization_goal="CONVERSATIONS", destination_type="INSTAGRAM_DIRECT",
                               bid_strategy="LOWEST_COST_WITHOUT_CAP", promoted_object={"page_id": page_id},
                               daily_budget=int(round(float(a["orcamento_diario"]) * 100)),
                               start_time=iso(a["inicio"]), end_time=iso(a["fim"], fim=True),
                               targeting=publico(a), status="PAUSED")["id"]
        salvar(est)
    if not reg.get("criativo"):
        reg["criativo"] = call("POST", f"{act}/adcreatives", name=f"[Robô] {a['nome']} · post",
                               object_id=page_id, instagram_user_id=ig_id, source_instagram_media_id=mid,
                               call_to_action={"type": "INSTAGRAM_MESSAGE", "value": {"link": "https://www.instagram.com"}})["id"]
        salvar(est)
    if not reg.get("anuncio"):
        reg["anuncio"] = call("POST", f"{act}/ads", name=f"[Robô] {a['nome']}", adset_id=reg["conjunto"],
                              creative={"creative_id": reg["criativo"]}, status="PAUSED")["id"]
    reg["status"] = "PAUSADO"
    reg["criado_em"] = dt.datetime.now(TZ).isoformat(timespec="minutes")
    salvar(est)
    print(f"Criado PAUSADO → {resumo(a)}")


def mudar(reg, status):
    for k in ("campanha", "conjunto", "anuncio"):
        if reg.get(k):
            call("POST", reg[k], status=status)
    reg["status"] = "ATIVO" if status == "ACTIVE" else "PAUSADO"


def relatorio(est):
    linhas = ["# Relatório dos anúncios", "", f"Atualizado em {dt.datetime.now(TZ):%d/%m/%Y %H:%M}", "",
              "| Anúncio | Status | Gasto | Alcance | Impressões | Conversas no Direct | Custo por conversa |",
              "|---|---|---|---|---|---|---|"]
    for nome, reg in est.items():
        if not reg.get("campanha"):
            continue
        st = call("GET", reg["anuncio"], fields="effective_status").get("effective_status", "?") if reg.get("anuncio") else "?"
        d = call("GET", f"{reg['campanha']}/insights", fields="spend,reach,impressions,actions", date_preset="maximum").get("data") or [{}]
        d = d[0]
        gasto = float(d.get("spend", 0) or 0)
        conv = sum(int(float(x["value"])) for x in d.get("actions", []) if x.get("action_type") == CONVERSA)
        cpc = f"R$ {gasto / conv:.2f}" if conv else "—"
        linhas.append(f"| {nome} | {st} | R$ {gasto:.2f} | {d.get('reach', 0)} | {d.get('impressions', 0)} | {conv} | {cpc} |")
    texto = "\n".join(linhas) + "\n"
    # No GitHub, o relatório vai para o resumo da execução (só quem tem acesso ao repositório vê),
    # e NÃO é salvo no repositório, que é público por causa das mídias.
    destino = os.environ.get("GITHUB_STEP_SUMMARY") or RELATORIO
    open(destino, "a" if destino != RELATORIO else "w", encoding="utf-8").write(texto)
    print(texto)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    for m in ("check", "simular", "criar", "ativar", "pausar", "relatorio"):
        g.add_argument(f"--{m}", action="store_true")
    ap.add_argument("--nome")
    a = ap.parse_args()

    cfg, est = carregar()
    if a.simular:
        for an in cfg:
            validar(an); print(("JÁ CRIADO · " if est.get(an["nome"], {}).get("anuncio") else "NOVO · ") + resumo(an))
        print("Nada foi criado (simulação).")
        return

    act = conta()
    page_id, page_name, ig_id, ig_user = accounts()
    if a.check:
        info = call("GET", act, fields="name,account_status,currency,amount_spent,timezone_name")
        status = {1: "ativa", 2: "desativada", 3: "com pagamento pendente", 7: "em análise", 9: "em período de carência"}
        print(f"Conta de anúncios: {info.get('name')} · {status.get(info.get('account_status'), info.get('account_status'))} · "
              f"moeda {info.get('currency')} · fuso {info.get('timezone_name')}")
        print(f"Página: {page_name} ({page_id}) · Instagram: @{ig_user} ({ig_id})")
        if info.get("currency") != "BRL":
            print("Atenção: a conta não está em reais; os valores de anuncios.json são lidos na moeda da conta.")
        for an in cfg:
            validar(an)
        print(f"anuncios.json OK: {len(cfg)} anúncio(s). Tudo certo.")
        return

    if a.criar:
        novos = [an for an in cfg if not est.get(an["nome"], {}).get("anuncio")]
        if not novos:
            print("Nenhum anúncio novo em anuncios.json."); return
        for an in novos:
            validar(an); criar(an, page_id, ig_id, act, est)
        print("Tudo foi criado PAUSADO. Para ligar: Run workflow → modo ativar → nome do anúncio.")
        return

    if a.ativar:
        if not a.nome or a.nome not in est:
            raise SystemExit(f"Diga o nome exato do anúncio para ativar. Criados: {', '.join(est) or 'nenhum'}")
        an = next((x for x in cfg if x["nome"] == a.nome), None)
        if an:
            validar(an); print("Ativando →", resumo(an))
        mudar(est[a.nome], "ACTIVE"); salvar(est)
        print("Ativado. A Meta revisa o anúncio (costuma levar de minutos a algumas horas) e depois ele começa a rodar.")
        return

    if a.pausar:
        alvos = [a.nome] if a.nome else list(est)
        for n in alvos:
            if n in est:
                mudar(est[n], "PAUSED"); print(f"Pausado: {n}")
        salvar(est)
        return

    if a.relatorio:
        relatorio(est)


if __name__ == "__main__":
    main()
