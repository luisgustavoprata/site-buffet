"""Ponto de entrada: monta a aplicação FastAPI.

Rodar localmente:  SEED_DEMO=true uvicorn app.main:app --reload
"""

import asyncio
import contextlib
import logging
import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from app import errors, webpush
from app.config import Settings
from app.database import Base, add_missing_columns, make_engine
from app.deps import client_ip, get_today
from app.ipguard import COOKIE, COUNTRY_URLS, VPN_URLS, IpGuard, env_sources, parse_ip
from app.models import utcnow
from app.notifications import run_due
from app.ratelimit import LoginLimiter
from app.routers import auth, dashboard, portfolio, push, quotes, site
from app.security import hash_password
from app.seed import DEMO_CLIENT, DEMO_OWNER, ensure_owner, seed_demo

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

# Só o próprio site carrega scripts; fontes do Google e imagens da própria API.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
)


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

    app = FastAPI(
        title="Site do Buffet",
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
    app.state.ipguard = IpGuard(settings.secret_key)
    app.state.ipguard.load_bundled()  # cópia da lista do Brasil, até baixar a atualizada
    app.state.push_sender = webpush.send  # os testes trocam por um envio de mentira
    app.state.dummy_hash = hash_password("senha-inexistente", settings.password_iterations)

    # ---------- Barreira de segurança por IP ----------

    open_paths = ("/health", "/sw.js", "/manifest.webmanifest", "/favicon.ico")
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
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        return response

    class ChallengeAnswer(BaseModel):
        token: str = Field(max_length=600)
        nonce: str = Field(max_length=32)

    @app.get("/_seguranca", include_in_schema=False)
    def challenge_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "seguranca.html", headers={"Cache-Control": "no-store"})

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
        dashboard.router,
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

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health", tags=["Sistema"], summary="Verifica se o site está no ar")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "demo": settings.seed_demo}

    return app


app = create_app()
