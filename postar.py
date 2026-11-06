"""Robô de posts do @walterribestrafego.

Publica no Instagram (e, se marcado, no Facebook) o que estiver em posts.json no dia e hora certos.
Tipos aceitos:
  post       uma foto (JPEG)                       → feed
  carrossel  2 a 10 fotos (JPEG)                   → feed
  reel       um vídeo MP4 (9:16, até 90 s)         → Reels (e aparece no feed)
  story      uma foto JPEG ou um vídeo MP4         → stories

Uso:
  python postar.py                 publica o que estiver na hora (ou atrasado hoje)
  python postar.py --check         confere token, Página, Instagram e limite de posts
  python postar.py --dry-run       manda o próximo post para o Instagram processar, sem publicar
  python postar.py --date AAAA-MM-DD [--time HH:MM]   publica agora o post daquele dia
"""
import argparse, datetime as dt, json, os, sys, time
from zoneinfo import ZoneInfo
from meta import call, accounts, media_url, esperar, ROOT

TZ = ZoneInfo("America/Sao_Paulo")
STATE = os.path.join(ROOT, "publicados.json")
ANTES = 14 * 60  # pode começar até 14 min antes e esperar o horário


def is_video(f):
    return f.lower().endswith((".mp4", ".mov"))


def ig_container(ig_id, item):
    tipo, files = item["tipo"], item["arquivos"]
    legenda = item.get("legenda", "")
    if tipo == "reel":
        p = {"media_type": "REELS", "video_url": media_url(files[0]), "caption": legenda, "share_to_feed": "true"}
        if item.get("capa"):
            p["cover_url"] = media_url(item["capa"])
        return esperar(call("POST", f"{ig_id}/media", **p)["id"], video=True)
    if tipo == "story":
        f = files[0]
        key = "video_url" if is_video(f) else "image_url"
        return esperar(call("POST", f"{ig_id}/media", media_type="STORIES", **{key: media_url(f)})["id"], video=is_video(f))
    if tipo == "post":
        return esperar(call("POST", f"{ig_id}/media", image_url=media_url(files[0]), caption=legenda)["id"])
    if tipo == "carrossel":
        filhos = []
        for f in files:
            k = "video_url" if is_video(f) else "image_url"
            extra = {"media_type": "VIDEO"} if is_video(f) else {}
            filhos.append(esperar(call("POST", f"{ig_id}/media", is_carousel_item="true", **extra, **{k: media_url(f)})["id"], video=is_video(f)))
        return esperar(call("POST", f"{ig_id}/media", media_type="CAROUSEL", children=",".join(filhos), caption=legenda)["id"])
    raise SystemExit(f"Tipo desconhecido em posts.json: {tipo}")


def publish_ig(ig_id, item):
    return call("POST", f"{ig_id}/media_publish", creation_id=ig_container(ig_id, item))["id"]


def publish_fb(page_id, item):
    """Facebook só para fotos e carrosséis de fotos (Reels e vídeos ficam só no Instagram)."""
    if item["tipo"] in ("reel",) or any(is_video(f) for f in item["arquivos"]):
        return "pulado (vídeo)"
    if item["tipo"] == "story":
        photo = call("POST", f"{page_id}/photos", url=media_url(item["arquivos"][0]), published="false")["id"]
        return call("POST", f"{page_id}/photo_stories", photo_id=photo).get("post_id") or photo
    fotos = [call("POST", f"{page_id}/photos", url=media_url(f), published="false")["id"] for f in item["arquivos"]]
    params = {"message": item.get("legenda", "")}
    for i, fid in enumerate(fotos):
        params[f"attached_media[{i}]"] = {"media_fbid": fid}
    return call("POST", f"{page_id}/feed", **params)["id"]


def chave(item):
    return f"{item['date']} {item['time']}"


def validar(sched):
    erros = []
    for s in sched:
        k = chave(s)
        for f in s.get("arquivos", []) + ([s["capa"]] if s.get("capa") else []):
            if not os.path.exists(os.path.join(ROOT, f)):
                erros.append(f"{k}: arquivo não encontrado: {f}")
            elif not is_video(f) and not f.lower().endswith((".jpg", ".jpeg")):
                erros.append(f"{k}: o Instagram só aceita foto em JPEG: {f}")
        n = len(s.get("arquivos", []))
        if s.get("tipo") == "carrossel" and not 2 <= n <= 10:
            erros.append(f"{k}: carrossel precisa de 2 a 10 arquivos")
        if s.get("tipo") in ("post", "reel", "story") and n != 1:
            erros.append(f"{k}: {s.get('tipo')} usa exatamente 1 arquivo")
        if s.get("tipo") == "reel" and not is_video(s["arquivos"][0]):
            erros.append(f"{k}: reel precisa de vídeo MP4")
        if len(s.get("legenda", "")) > 2200:
            erros.append(f"{k}: legenda passa de 2.200 caracteres")
    if erros:
        raise SystemExit("posts.json com problema:\n- " + "\n- ".join(erros))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--time")
    a = ap.parse_args()

    sched = json.load(open(os.path.join(ROOT, "posts.json"), encoding="utf-8"))
    validar(sched)
    page_id, page_name, ig_id, ig_user = accounts()
    print(f"Página: {page_name} ({page_id}) · Instagram: @{ig_user} ({ig_id})")
    if not ig_id:
        raise SystemExit("A Página não tem Instagram comercial vinculado.")
    if a.check:
        lim = call("GET", f"{ig_id}/content_publishing_limit", fields="quota_usage,config")
        print("Limite de publicação:", json.dumps(lim.get("data", lim)))
        print(f"posts.json OK: {len(sched)} item(ns) no calendário.")
        print("Tudo certo: token e contas OK.")
        return

    now = dt.datetime.now(TZ)
    day = a.date or now.date().isoformat()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}

    def quando(s):
        hh, mm = map(int, s["time"].split(":"))
        return now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    do_dia = [s for s in sched if s["date"] == day and (not a.time or s["time"] == a.time)]
    if a.dry_run:
        item = do_dia[0] if do_dia else None
        if not item and not a.date:
            item = next((s for s in sorted(sched, key=chave) if chave(s) >= f"{day} {now:%H:%M}"), None)
        if not item:
            print(f"Nada agendado a partir de {day}."); return
        print(f"{chave(item)}: {item['tipo']} · {', '.join(item['arquivos'])}")
        c = ig_container(ig_id, item)
        print(f"Teste OK: o Instagram aceitou ({c}). Nada foi publicado.")
        return

    def feito(s):
        d = state.get(chave(s), {})
        return bool(d.get("instagram") and (d.get("facebook") or not s.get("facebook")))

    hoje = now.date().isoformat()

    def na_hora(s):
        if day != hoje:
            return True
        return (quando(s) - now).total_seconds() <= (0 if a.date else ANTES)

    fila = [s for s in do_dia if not feito(s) and na_hora(s)]
    if not fila:
        print(f"Nada pendente para {day} agora."); return

    erros = []
    for item in fila:
        print(f"{chave(item)}: {item['tipo']} · {', '.join(item['arquivos'])}")
        done = state.get(chave(item), {})
        wait = (quando(item) - dt.datetime.now(TZ)).total_seconds()
        if wait > 0 and day == hoje and not a.date:
            print(f"Aguardando {int(wait)}s…"); time.sleep(wait)
        redes = [("instagram", publish_ig, ig_id)] + ([("facebook", publish_fb, page_id)] if item.get("facebook") else [])
        for net, fn, acc in redes:
            if done.get(net):
                continue
            try:
                done[net] = fn(acc, item)
                print(f"Publicado no {net}: {done[net]}")
            except SystemExit as e:
                erros.append(f"{net}: {e}"); print(f"Falhou no {net}: {e}")
        state[chave(item)] = done
        json.dump(state, open(STATE, "w"), indent=2, ensure_ascii=False)
    if erros:
        sys.exit("; ".join(erros))


if __name__ == "__main__":
    main()
