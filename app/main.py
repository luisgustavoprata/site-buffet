"""Ponto de entrada: monta a aplicação FastAPI.

Rodar localmente:  SEED_DEMO=true uvicorn app.main:app --reload
"""

import asyncio
import contextlib
import logging
import random
import re
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from app import errors, webpush
from app.config import Settings
from app.database import Base, add_missing_columns, make_engine
from app.deps import client_ip, get_today
from app.ipguard import COOKIE, COUNTRY_URLS, VPN_URLS, IpGuard, env_sources, parse_ip
from app.models import Image, SiteContent, utcnow
from app.notifications import run_due
from app.ratelimit import LoginLimiter
from app.routers import auth, gestao, menu, portfolio, push, quotes, site
from app.security import hash_password
from app.seed import DEMO_CLIENT, DEMO_OWNER, ensure_owner, remove_demo_accounts, seed_demo
from app.services import SITE_ID, delete_orphan_images

__version__ = "1.0.0"
STATIC_DIR = Path(__file__).parent / "static"

DESCRIPTION = """
API do site de um buffet: apresentação, portfólio de eventos e pedidos de orçamento com
conversa entre o cliente e a administração.

A [página inicial](/) é o site completo, feito sobre esta mesma API.
"""

DEMO_NOTE = """

**Demonstração:** clique em **Authorize** e entre como cliente (`{client}` / `{password}`)
ou como administração (`{owner}` / `{password}`).
"""

# Só o próprio site carrega scripts (mais as bibliotecas da aba Resultados, conferidas por
# hash); nenhum script escrito dentro da página roda. Fontes do Google, imagens do site.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' https://cdn.jsdelivr.net https://cdn.sheetjs.com",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
)
# A documentação da API (só fora do site de verdade) usa o Swagger, que precisa de mais.
DOCS_CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "frame-ancestors 'none'",
    ]
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
MAX_BODY_BYTES = 12 * 1024 * 1024  # fotos de até 10 MB, com folga para o resto do formulário


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        add_missing_columns(engine)
        with session_factory.begin() as db:
            ensure_owner(db, settings)
            if settings.seed_demo:
                seed_demo(db, get_today(settings), settings.password_iterations)
            else:
                remove_demo_accounts(db, settings)
            delete_orphan_images(db)  # o servidor reinicia com frequência no plano gratuito
        tasks = []
        if settings.push_scheduler:
            tasks.append(asyncio.create_task(push_loop()))
        if settings.ipguard_enabled and settings.ipguard_refresh:
            tasks.append(asyncio.create_task(ipguard_loop()))
        yield
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        engine.dispose()

    async def ipguard_loop() -> None:
        """Baixa as listas de IPs (Brasil e VPN/datacenter) ao iniciar e uma vez por dia."""
        country = env_sources(settings.ipguard_country_sources, COUNTRY_URLS)
        vpn = env_sources(settings.ipguard_vpn_sources, VPN_URLS)
        while True:
            await asyncio.to_thread(app.state.ipguard.refresh, country, vpn)
            await asyncio.sleep(24 * 3600)

    def push_tick() -> None:
        with session_factory.begin() as db:
            run_due(db, settings, utcnow(), app.state.push_sender, random.Random())

    async def push_loop() -> None:
        """Confere a cada minuto se chegou a hora de alguma notificação programada."""
        await asyncio.sleep(15)
        while True:
            try:
                await asyncio.to_thread(push_tick)
            except Exception:
                logging.getLogger(__name__).exception("Falha ao enviar notificações")
            await asyncio.sleep(60)

    description = DESCRIPTION
    if settings.seed_demo:
        description += DEMO_NOTE.format(
            client=DEMO_CLIENT[0], owner=DEMO_OWNER[0], password=DEMO_CLIENT[1]
        )

    # No site de verdade, a documentação da API não fica aberta ao público.
    public_docs = settings.seed_demo or settings.environment != "production"
    app = FastAPI(
        title="Site do Buffet",
        docs_url="/docs" if public_docs else None,
        redoc_url="/redoc" if public_docs else None,
        openapi_url="/openapi.json" if public_docs else None,
        version=__version__,
        description=description,
        lifespan=lifespan,
        license_info={"name": "MIT"},
        openapi_tags=[
            {"name": "Conta", "description": "Cadastro e login dos clientes."},
            {"name": "Site", "description": "Apresentação do buffet e envio de fotos."},
            {"name": "Portfólio", "description": "Eventos realizados, com fotos."},
            {"name": "Orçamentos", "description": "Pedidos de orçamento e conversa."},
            {"name": "Notificações", "description": "Avisos no celular e no computador."},
            {"name": "Resultados", "description": "Números da planilha do buffet (painel)."},
            {"name": "Sistema"},
        ],
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.login_limiter = LoginLimiter(
        settings.login_max_attempts, settings.login_window_seconds
    )
    app.state.register_limiter = LoginLimiter(5, 3600)  # contas novas por conexão, por hora
    app.state.ipguard = IpGuard(settings.secret_key)
    app.state.ipguard.load_bundled()  # cópia da lista do Brasil, até baixar a atualizada
    app.state.push_sender = webpush.send  # os testes trocam por um envio de mentira
    app.state.dummy_hash = hash_password("senha-inexistente", settings.password_iterations)

    # ---------- Barreira de segurança por IP ----------

    open_paths = (
        "/health",
        "/sw.js",
        "/manifest.webmanifest",
        "/favicon.ico",
        "/robots.txt",
        "/capa.jpg",
    )
    sensitive_paths = ("/auth/token", "/auth/register")

    def wants_page(request: Request) -> bool:
        return request.method == "GET" and (
            request.url.path in ("/", "/docs") or "text/html" in request.headers.get("accept", "")
        )

    @app.middleware("http")
    async def ip_barrier(request: Request, call_next):
        path = request.url.path
        if (
            not settings.ipguard_enabled
            or path in open_paths
            or path.startswith(("/static/", "/_seguranca"))
        ):
            return await call_next(request)
        guard: IpGuard = app.state.ipguard
        ip = parse_ip(client_ip(request))
        sensitive = request.method not in ("GET", "HEAD", "OPTIONS") or path in sensitive_paths
        decision = guard.decide(
            ip, passed=guard.has_pass(ip, request.cookies.get(COOKIE)), sensitive=sensitive
        )
        if decision.action == "ok":
            return await call_next(request)
        if decision.action == "slow_down":
            return JSONResponse(
                {"detail": "Muitos acessos em pouco tempo. Aguarde alguns minutos."},
                status_code=429,
                headers={"Retry-After": "300"},
            )
        # Robôs de busca confirmados e prévias de link (só a página inicial) seguem normais.
        agent = request.headers.get("user-agent", "")
        if request.method == "GET" and (
            (path == "/" and guard.is_preview_bot(agent))
            or await asyncio.to_thread(guard.is_search_bot, ip, agent)
        ):
            return await call_next(request)
        if wants_page(request):
            return FileResponse(
                STATIC_DIR / "seguranca.html",
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(
            {"detail": "Confirme a verificação de segurança para continuar.", "challenge": True},
            status_code=403,
        )

    # Registrado depois da barreira: vale também para a página de verificação.
    production = settings.environment == "production"
    docs_paths = ("/docs", "/redoc")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        csp = (
            DOCS_CONTENT_SECURITY_POLICY
            if request.url.path.startswith(docs_paths)
            else CONTENT_SECURITY_POLICY
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if production:
            # O navegador passa a usar só HTTPS neste endereço, mesmo se alguém digitar http://.
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    # Registrado por último, roda primeiro: recusa envios grandes antes de ler o corpo.
    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse(
                {"detail": "Envio grande demais. Fotos de até 10 MB."}, status_code=413
            )
        return await call_next(request)

    class ChallengeAnswer(BaseModel):
        token: str = Field(max_length=600)
        nonce: str = Field(max_length=32)

    @app.get("/_seguranca", include_in_schema=False)
    def challenge_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "seguranca.html", headers={"Cache-Control": "no-store"})

    @app.get("/_seguranca/contato", include_in_schema=False)
    def challenge_contact() -> JSONResponse:
        """WhatsApp do buffet e a capa do site, para a página de verificação."""
        with session_factory() as db:
            site = db.get(SiteContent, SITE_ID)
            digits = "".join(c for c in (site.phone or "") if c.isdigit()) if site else ""
            cover = site.hero_image_id if site else None
        return JSONResponse(
            {
                "whatsapp": f"https://wa.me/55{digits}" if len(digits) >= 10 else None,
                "cover": "/_seguranca/capa" if cover else None,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/_seguranca/capa", include_in_schema=False)
    @app.get("/capa.jpg", include_in_schema=False)
    def challenge_cover() -> Response:
        # A capa já é pública no site; aqui ela abre também para quem ainda não passou.
        with session_factory() as db:
            site = db.get(SiteContent, SITE_ID)
            image = db.get(Image, site.hero_image_id) if site and site.hero_image_id else None
            if image is None or image.access_key:
                return JSONResponse({"detail": "Sem capa."}, status_code=404)
            return Response(
                image.data,
                media_type=image.content_type,
                headers={"Cache-Control": "public, max-age=3600"},
            )

    @app.get("/_seguranca/desafio", include_in_schema=False)
    def new_challenge(request: Request) -> JSONResponse:
        challenge = app.state.ipguard.new_challenge(parse_ip(client_ip(request)))
        return JSONResponse(challenge, headers={"Cache-Control": "no-store"})

    @app.post("/_seguranca/verificar", include_in_schema=False)
    def check_challenge(answer: ChallengeAnswer, request: Request) -> JSONResponse:
        ip = parse_ip(client_ip(request))
        cookie = app.state.ipguard.verify(ip, answer.token, answer.nonce)
        if cookie is None:
            return JSONResponse({"ok": False}, status_code=403)
        response = JSONResponse({"ok": True})
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie(
            COOKIE, cookie, max_age=24 * 3600, httponly=True, samesite="lax", secure=https
        )
        return response

    errors.register(app)
    for router in (
        auth.router,
        site.router,
        portfolio.router,
        quotes.router,
        push.router,
        gestao.router,
        menu.router,
    ):
        app.include_router(router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        # Fica na raiz do site para receber as notificações de todas as páginas.
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json"
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> RedirectResponse:
        return RedirectResponse("/static/favicon.png", status_code=301)

    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        # O site todo pode aparecer no Google; as rotas da API não têm o que mostrar.
        return PlainTextResponse(
            "User-agent: *\nAllow: /$\nAllow: /static/\nAllow: /media/\nDisallow: /\n"
        )

    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/", include_in_schema=False)
    def home(request: Request) -> HTMLResponse:
        # Prévia do link no WhatsApp, Instagram e Google: nome, frase e foto da capa do site.
        with session_factory() as db:
            site = db.get(SiteContent, SITE_ID)
            name = (site.business_name if site else "") or "Buffet"
            text = (site.hero_text or site.tagline) if site else ""
            cover = site.hero_image_id if site else None
        base = str(request.base_url).rstrip("/")
        if request.headers.get("x-forwarded-proto") == "https":
            base = base.replace("http://", "https://", 1)
        tags = [
            ("og:type", "website"),
            ("og:locale", "pt_BR"),
            ("og:site_name", name),
            ("og:title", name),
            ("og:description", text),
            ("og:url", f"{base}/"),
        ]
        if cover:
            # A capa por um endereço aberto: os robôs de prévia (WhatsApp etc.) vêm de
            # datacenters e cairiam na verificação de segurança em /media.
            tags.append(("og:image", f"{base}/capa.jpg"))
        meta = "".join(
            f'\n  <meta property="{key}" content="{escape(value)}">' for key, value in tags if value
        )
        card = "summary_large_image" if cover else "summary"
        meta += f'\n  <meta name="twitter:card" content="{card}">'
        page = index_html.replace(
            "<title>Brunoise Gastronomia</title>", f"<title>{escape(name)}</title>", 1
        )
        if text:
            page = re.sub(
                r'<meta name="description" content="[^"]*">',
                lambda _m: f'<meta name="description" content="{escape(text)}">',
                page,
                count=1,
            )
        return HTMLResponse(page.replace("</head>", f"{meta}\n</head>", 1))

    @app.get("/health", tags=["Sistema"], summary="Verifica se o site está no ar")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "demo": settings.seed_demo}

    return app


app = create_app()
