"""Vigia do robô de posts do @walterribestrafego.

Fica rodando por algumas horas e:
  - publica cada post de posts.json na hora certa;
  - a cada 30 minutos confere no Instagram se os posts dos últimos dias estão mesmo no ar;
  - se algum não saiu (ou sumiu), publica de novo — um atrasado por vez, pra não despejar vários juntos;
  - registra tudo em publicados.json e no histórico do repositório.

O GitHub atrasa e pula agendamentos quando está cheio, por isso o vigia não depende deles:
no fim ele mesmo se religa (veja .github/workflows/posts.yml).

Uso:  python vigia.py --horas 5.6
"""
import argparse, datetime as dt, json, os, subprocess, time
from postar import TZ, STATE, chave, validar, publish_ig, publish_fb
from meta import call, accounts, ROOT

JANELA = dt.timedelta(days=3)        # até quantos dias pra trás ele confere e recupera
CICLO = dt.timedelta(minutes=30)     # conferência no Instagram
NO_HORARIO = dt.timedelta(minutes=35)


def agora():
    return dt.datetime.now(TZ)


def quando(s):
    return dt.datetime.strptime(chave(s), "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def log(msg):
    print(f"[{agora():%d/%m %H:%M}] {msg}", flush=True)


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def atualizar_repo():
    """Pega mudanças novas da agenda (posts.json) antes de cada rodada."""
    git("pull", "--rebase", "-q")


def carregar():
    sched = json.load(open(os.path.join(ROOT, "posts.json"), encoding="utf-8"))
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    return sched, state


def salvar(state, msg):
    json.dump(state, open(STATE, "w"), indent=2, ensure_ascii=False)
    git("add", "publicados.json")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return
    git("commit", "-q", "-m", msg)
    for _ in range(5):
        git("pull", "--rebase", "-q")
        if git("push", "-q").returncode == 0:
            return
        time.sleep(5)
    log("Aviso: não consegui enviar o registro agora; tento de novo na próxima rodada.")


def feito(state, s):
    d = state.get(chave(s), {})
    return bool(d.get("instagram") and (d.get("facebook") or not s.get("facebook")))


def existe(media_id):
    """True se o post ainda está no Instagram. Em erro de rede, assume que está (pra nunca duplicar)."""
    try:
        call("GET", media_id, fields="id")
        return True
    except SystemExit as e:
        m = str(e)
        if "does not exist" in m or "Unsupported get request" in m or '"code":100' in m:
            return False
        log(f"Não deu pra conferir {media_id} agora ({m[:120]}). Fica pra próxima.")
        return True


def publicar(item, state, ig_id, page_id):
    k = chave(item)
    done = state.get(k, {})
    redes = [("instagram", publish_ig, ig_id)] + ([("facebook", publish_fb, page_id)] if item.get("facebook") else [])
    ok = True
    for net, fn, acc in redes:
        if done.get(net):
            continue
        try:
            done[net] = fn(acc, item)
            log(f"{k} {item['tipo']}: publicado no {net} ({done[net]})")
        except SystemExit as e:
            ok = False
            log(f"{k} {item['tipo']}: falhou no {net}: {str(e)[:300]}")
    state[k] = done
    salvar(state, f"Vigia: {k} {item['tipo']} {'publicado' if ok else 'com erro'}")
    return ok


def rodada(ig_id, page_id, conferir):
    atualizar_repo()
    sched, state = carregar()
    try:
        validar(sched)
    except SystemExit as e:
        log(f"posts.json com problema, nada publicado nesta rodada:\n{e}")
        return sched
    now = agora()
    recentes = [s for s in sched if now - JANELA <= quando(s) <= now]

    # 1) confere no Instagram o que já foi registrado como publicado
    if conferir:
        sumidos = 0
        for s in recentes:
            d = state.get(chave(s), {})
            if s["tipo"] == "story" or not d.get("instagram"):
                continue  # story some sozinho em 24 h: não dá pra conferir
            if not existe(d["instagram"]):
                log(f"{chave(s)} {s['tipo']}: não está mais no Instagram. Vou publicar de novo.")
                d.pop("instagram", None); state[chave(s)] = d; sumidos += 1
        if sumidos:
            salvar(state, f"Vigia: {sumidos} post(s) não encontrados no Instagram")
        ok = sum(1 for s in recentes if feito(state, s))
        log(f"Conferência: {ok} de {len(recentes)} posts dos últimos 3 dias estão no ar.")

    # 2) publica o que está na hora + no máximo um atrasado
    pend = sorted([s for s in recentes if not feito(state, s)], key=quando)
    pend = [s for s in pend if s["tipo"] != "story" or quando(s).date() == now.date()]  # story velho não faz sentido
    agora_ = [s for s in pend if now - quando(s) <= NO_HORARIO]
    atrasados = [s for s in pend if s not in agora_]
    if atrasados:
        log(f"{len(atrasados)} post(s) atrasado(s): {', '.join(chave(s) for s in atrasados)}. Publicando um agora.")
    for s in agora_ + atrasados[:1]:
        publicar(s, state, ig_id, page_id)
    return sched


def proxima_parada(sched, ultima_conf):
    """Acorda no próximo horário de post ou na próxima conferência, o que vier antes."""
    now = agora()
    alvo = ultima_conf + CICLO
    futuros = [quando(s) for s in sched if quando(s) > now]
    if futuros:
        alvo = min(alvo, min(futuros))
    return max(alvo, now + dt.timedelta(seconds=20))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=float, default=5.6)
    a = ap.parse_args()
    fim = agora() + dt.timedelta(hours=a.horas)
    log(f"Vigia ligado até {fim:%d/%m %H:%M}.")

    ig_id = page_id = None
    ultima_conf = agora() - CICLO  # confere logo de cara
    sched = []
    while agora() < fim:
        try:
            if not ig_id:
                page_id, _, ig_id, ig_user = accounts()
                log(f"Instagram @{ig_user} conectado.")
            conferir = agora() - ultima_conf >= CICLO - dt.timedelta(minutes=1)
            sched = rodada(ig_id, page_id, conferir) or sched
            if conferir:
                ultima_conf = agora()
        except SystemExit as e:
            log(f"Erro nesta rodada: {str(e)[:300]}. Tento de novo em seguida.")
            ig_id = None  # refaz a conexão (ex.: chave trocada)
        except Exception as e:  # nunca deixa o vigia cair
            log(f"Erro inesperado: {e!r}. Tento de novo em seguida.")
        alvo = min(proxima_parada(sched, ultima_conf), fim)
        espera = (alvo - agora()).total_seconds()
        if espera > 0:
            time.sleep(espera)
    log("Vigia encerrado. O próximo assume daqui a pouco.")


if __name__ == "__main__":
    main()
