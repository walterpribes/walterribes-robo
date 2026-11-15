"""Conexão com a API da Meta (Instagram, Facebook e Anúncios) — usada pelos dois robôs.

Segredos no GitHub (Settings → Secrets and variables → Actions):
  META_PAGE_TOKEN   token da Página do Facebook ligada ao @walterribestrafego (não expira)
  META_AD_ACCOUNT   número da conta de anúncios (só os dígitos, sem "act_") — só para anúncios
Opcionais (descobertos sozinhos a partir do token): META_PAGE_ID, IG_USER_ID
"""
import json, os, time
import urllib.request, urllib.parse, urllib.error

API = "https://graph.facebook.com/v26.0"
ROOT = os.path.dirname(os.path.abspath(__file__))


_PAGE_TOKEN = None  # preenchido se o segredo tiver a chave pessoal em vez da chave da Página


def call(method, path, **params):
    """Chama a Graph API. O token vai só no cabeçalho: nunca na URL nem nos registros."""
    token = _PAGE_TOKEN or os.environ.get("META_PAGE_TOKEN", "").strip()
    if not token:
        raise SystemExit("Falta o segredo META_PAGE_TOKEN no GitHub.")
    headers = {"Authorization": f"Bearer {token}"}
    for k, v in list(params.items()):
        if isinstance(v, (dict, list)):
            params[k] = json.dumps(v, ensure_ascii=False)
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}", headers=headers)
    else:
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").replace(token, "***")
        if _PAGE_TOKEN:
            body = body.replace(_PAGE_TOKEN, "***")
        raise SystemExit(f"Erro da Meta em {method} {path}: {body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Sem conexão com a Meta em {method} {path}: {e.reason}")


def accounts():
    """Página, nome, Instagram comercial vinculado e @ do Instagram."""
    global _PAGE_TOKEN
    page_id = os.environ.get("META_PAGE_ID")
    ig_id = os.environ.get("IG_USER_ID")
    try:
        me = call("GET", page_id or "me", fields="id,name,instagram_business_account{id,username}")
    except SystemExit as e:
        if "instagram_business_account" not in str(e):
            raise
        # O segredo tem a chave da conta pessoal: pega a chave da Página que tem o Instagram ligado.
        pages = call("GET", "me/accounts", fields="id,name,access_token,instagram_business_account{id,username}").get("data", [])
        pages = [p for p in pages if p.get("instagram_business_account") and (not page_id or p["id"] == page_id)]
        if not pages:
            raise SystemExit("A chave do segredo é pessoal e nenhuma Página com Instagram foi encontrada em me/accounts.")
        me = pages[0]
        _PAGE_TOKEN = me.pop("access_token")
        print("Aviso: META_PAGE_TOKEN tem a chave pessoal (vence em ~60 dias). Usando a chave da Página tirada dela.")
    iga = me.get("instagram_business_account") or {}
    return me["id"], me.get("name"), ig_id or iga.get("id"), iga.get("username")


def media_url(path):
    """Endereço público do arquivo neste repositório (a Meta baixa daqui)."""
    repo = os.environ.get("GITHUB_REPOSITORY", "walterpribes/walterribes-robo")
    branch = os.environ.get("MEDIA_BRANCH", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{urllib.parse.quote(path)}"


def esperar(container, video=False):
    """Espera o Instagram processar a mídia. Vídeo pode levar alguns minutos."""
    passo, vezes = (10, 36) if video else (5, 40)
    for _ in range(vezes):
        st = call("GET", container, fields="status_code").get("status_code")
        if st == "FINISHED":
            return container
        if st in ("ERROR", "EXPIRED"):
            info = call("GET", container, fields="status")
            raise SystemExit(f"Instagram recusou a mídia ({st}): {info.get('status', '')}")
        time.sleep(passo)
    raise SystemExit("Instagram demorou demais para processar a mídia.")
