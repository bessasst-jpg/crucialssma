"""Cliente mínimo da Instagram API (login do Instagram / graph.instagram.com).

Só usa a biblioteca padrão do Python. Cada método devolve o JSON da API
ou levanta IGError com a mensagem da Meta.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class IGError(Exception):
    pass


class IG:
    def __init__(self, token, user_id="me", base="https://graph.instagram.com", version="v23.0"):
        self.token = token
        self.user_id = user_id or "me"
        self.base = base.rstrip("/")
        self.version = version
        # Tokens do login do Facebook / login unificado (SUAT) começam com "EAA"
        # e só funcionam em graph.facebook.com.
        if token.startswith("EAA") and "graph.instagram.com" in self.base:
            self.base = "https://graph.facebook.com"
        self.facebook = "graph.facebook.com" in self.base

    # ---------- baixo nível ----------
    def _req(self, method, path, params=None, versioned=True):
        params = dict(params or {})
        params["access_token"] = self.token
        prefix = f"{self.base}/{self.version}" if versioned else self.base
        url = f"{prefix}/{path.lstrip('/')}"
        body = None
        if method == "GET":
            url += "?" + urllib.parse.urlencode(params)
        else:
            body = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(url, data=body, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode()).get("error", {})
                msg = err.get("error_user_msg") or err.get("message") or str(e)
            except Exception:
                msg = str(e)
            raise IGError(msg) from None
        except urllib.error.URLError as e:
            raise IGError(f"Falha de conexão: {e.reason}") from None

    def get(self, path, **params):
        return self._req("GET", path, params)

    def post(self, path, **params):
        return self._req("POST", path, params)

    # ---------- conta ----------
    def profile(self):
        fields = "username,name,biography,website,followers_count,follows_count,media_count,profile_picture_url"
        if self.facebook:
            if self.user_id == "me":
                self.user_id = self._find_ig_account()
            return self.get(self.user_id, fields=fields)
        data = self.get("me", fields="user_id," + fields)
        # Com login do Instagram, "user_id" é o id da conta profissional.
        if self.user_id == "me":
            self.user_id = data.get("user_id") or data.get("id")
        return data

    def _find_ig_account(self):
        """No login do Facebook, procura a conta do Instagram ligada às páginas do token."""
        try:
            pages = self.get("me/accounts", fields="instagram_business_account").get("data", [])
        except IGError:
            pages = []
        for p in pages:
            if p.get("instagram_business_account"):
                return p["instagram_business_account"]["id"]
        raise IGError("Não achei a conta do Instagram deste token. Coloque o ID da conta do Instagram "
                      "em IG_USER_ID no config.env (aparece no painel da Meta, na configuração do app).")

    def refresh_token(self):
        """Renova o token de longa duração (válido por mais 60 dias)."""
        if self.facebook:  # token de usuário do sistema não expira
            return {"access_token": self.token}
        return self._req(
            "GET", "refresh_access_token", {"grant_type": "ig_refresh_token"}, versioned=False
        )

    def account_insights(self, metrics, period="day", since=None, until=None, metric_type=None):
        params = {"metric": ",".join(metrics), "period": period}
        if since:
            params["since"] = int(since)
        if until:
            params["until"] = int(until)
        if metric_type:
            params["metric_type"] = metric_type
        return self.get(f"{self.user_id}/insights", **params).get("data", [])

    # ---------- mídia ----------
    def media(self, max_items=100):
        fields = ("id,caption,media_type,media_product_type,permalink,media_url,"
                  "thumbnail_url,timestamp,like_count,comments_count")
        out, page = [], self.get(f"{self.user_id}/media", fields=fields, limit=50)
        while True:
            out.extend(page.get("data", []))
            nxt = page.get("paging", {}).get("next")
            if not nxt or len(out) >= max_items:
                return out[:max_items]
            with urllib.request.urlopen(nxt, timeout=60) as r:
                page = json.loads(r.read().decode())

    def media_insights(self, media_id):
        """Tenta o conjunto completo de métricas; se a API recusar, usa um menor."""
        for metrics in ("reach,saved,shares,total_interactions,views",
                        "reach,saved,shares,total_interactions",
                        "reach,saved"):
            try:
                data = self.get(f"{media_id}/insights", metric=metrics).get("data", [])
                return {m["name"]: _metric_value(m) for m in data}
            except IGError:
                continue
        return {}

    # ---------- publicação ----------
    def create_container(self, media_type, urls, caption=""):
        urls = [u for u in urls if u]
        if not urls:
            raise IGError("Informe a URL pública da imagem ou vídeo.")
        if media_type == "CAROUSEL":
            children = []
            for u in urls[:10]:
                key = "video_url" if _is_video(u) else "image_url"
                extra = {"media_type": "VIDEO"} if _is_video(u) else {}
                c = self.post(f"{self.user_id}/media", is_carousel_item="true", **{key: u}, **extra)
                children.append(c["id"])
            for cid in children:
                self.wait_container(cid)
            return self.post(f"{self.user_id}/media", media_type="CAROUSEL",
                             children=",".join(children), caption=caption)["id"]
        if media_type == "REELS":
            return self.post(f"{self.user_id}/media", media_type="REELS",
                             video_url=urls[0], caption=caption, share_to_feed="true")["id"]
        if media_type == "STORIES":
            key = "video_url" if _is_video(urls[0]) else "image_url"
            return self.post(f"{self.user_id}/media", media_type="STORIES", **{key: urls[0]})["id"]
        return self.post(f"{self.user_id}/media", image_url=urls[0], caption=caption)["id"]

    def wait_container(self, container_id, timeout=600):
        start = time.time()
        while time.time() - start < timeout:
            st = self.get(container_id, fields="status_code,status")
            code = st.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise IGError(f"Processamento da mídia falhou: {st.get('status', code)}")
            time.sleep(5)
        raise IGError("Tempo esgotado esperando a mídia processar.")

    def publish(self, container_id):
        self.wait_container(container_id)
        media_id = self.post(f"{self.user_id}/media_publish", creation_id=container_id)["id"]
        try:
            permalink = self.get(media_id, fields="permalink").get("permalink")
        except IGError:
            permalink = None
        return media_id, permalink

    def publishing_limit(self):
        data = self.get(f"{self.user_id}/content_publishing_limit", fields="config,quota_usage")
        return (data.get("data") or [{}])[0]


def _metric_value(m):
    if "total_value" in m:
        return m["total_value"].get("value", 0)
    vals = m.get("values") or [{}]
    return vals[-1].get("value", 0)


def _is_video(url):
    return url.lower().split("?")[0].endswith((".mp4", ".mov", ".m4v"))
