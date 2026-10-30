"""Conta da administração e conteúdo de demonstração.

- `ensure_owner`: cria a conta da dona do buffet a partir de OWNER_EMAIL e OWNER_PASSWORD.
- `seed_demo`: preenche um site de exemplo (textos, ilustrações, portfólio, um cliente e uma
  conversa) para quem quer conhecer o projeto. Só roda com o banco vazio.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.images import process_upload
from app.models import (
    BioPhoto,
    Dashboard,
    Event,
    EventComment,
    EventLike,
    EventPhoto,
    Image,
    Message,
    Quote,
    QuoteStatus,
    Role,
    SiteContent,
    User,
)
from app.security import hash_password
from app.services import SITE_ID

DEMO_DIR = Path(__file__).parent / "demo"
DEMO_OWNER = ("helena@buffet.dev", "demo12345")
DEMO_CLIENT = ("marcos@cliente.dev", "demo12345")


def ensure_owner(db: Session, settings: Settings) -> None:
    if not (settings.owner_email and settings.owner_password):
        return
    user = db.scalar(select(User).where(User.email == settings.owner_email))
    if user is None:
        db.add(
            User(
                name=settings.owner_name,
                email=settings.owner_email,
                role=Role.OWNER,
                password_hash=hash_password(settings.owner_password, settings.password_iterations),
            )
        )
    elif user.role != Role.OWNER:
        user.role = Role.OWNER


def _image(db: Session, name: str) -> int:
    processed = process_upload((DEMO_DIR / f"{name}.jpg").read_bytes())
    image = Image(
        data=processed.data,
        content_type=processed.content_type,
        width=processed.width,
        height=processed.height,
    )
    db.add(image)
    db.flush()
    return image.id


# Textos de exemplo. Nome e marca são da Brunoise Gastronomia; a história, a chef e os
# eventos são ilustrativos e devem ser trocados pela dona no painel.
DEMO_TEXTS = {
    "business_name": "Brunoise Gastronomia",
    "tagline": "Gastronomia para os dias mais importantes",
    "hero_title": "Cada detalhe feito com cuidado, cada sabor pensado para você.",
    "hero_text": (
        "Casamentos, aniversários e eventos de empresa com cardápio feito sob medida, "
        "do primeiro canapé ao último cafezinho."
    ),
    "owner_name": "Helena Duarte",
    "owner_role": "Chef e fundadora",
    "bio": (
        "Cresci na cozinha da minha avó, ajudando a abrir massa antes de saber escrever o "
        "meu nome. Foi lá que aprendi que comida boa é a que faz as pessoas ficarem mais um "
        "pouco à mesa.\n\n"
        "Me formei em Gastronomia, trabalhei em restaurantes e cozinhas de hotel e, em cada "
        "evento, pensava em como seria servir aquela comida com o carinho de casa. Hoje cuido "
        "pessoalmente de cada cardápio: converso com você, provo junto e acompanho a festa do "
        "início ao fim."
    ),
    "history_title": "Por que Brunoise",
    "history": (
        "Brunoise é um dos cortes mais delicados da cozinha francesa: legumes em cubinhos de "
        "poucos milímetros, todos do mesmo tamanho. É um corte que não aceita pressa e pede "
        "técnica, paciência e atenção a cada pedaço.\n\n"
        "Foi esse cuidado que escolhemos como nome. Cada evento é preparado do mesmo jeito: "
        "ouvindo você, montando o cardápio junto e cuidando de cada detalhe, da montagem da "
        "mesa ao último prato servido."
    ),
    "founded_year": None,
    "city": "",
    "phone": "",
    "email": "",
    "instagram": "",
}
OLD_DEMO_NAME = "Buffet Alecrim"


def _refresh_old_demo(db: Session) -> None:
    """Demonstração criada antes da marca Brunoise: troca só os textos (fotos ficam)."""
    site = db.get(SiteContent, SITE_ID)
    if site is not None and site.business_name == OLD_DEMO_NAME:
        for field, value in DEMO_TEXTS.items():
            setattr(site, field, value)


def _site_is_blank(db: Session) -> bool:
    """Sem textos, fotos nem eventos: só o conteúdo padrão criado na primeira visita."""
    site = db.get(SiteContent, SITE_ID)
    if site is None:
        return True
    filled = (
        site.bio
        or site.history
        or site.hero_image_id
        or site.owner_image_id
        or site.history_image_id
    )
    return not filled and db.scalar(select(Event.id).limit(1)) is None


def seed_demo(db: Session, today: date, iterations: int) -> None:
    if db.scalar(select(User.id).where(User.email == DEMO_OWNER[0])) is not None:
        _refresh_old_demo(db)
        _demo_reactions(db)
        _demo_dashboard(db)
        return  # a demonstração já existe: reiniciar o servidor não duplica nada
    if not _site_is_blank(db):
        return  # o site já tem conteúdo de verdade: a demonstração não apaga nada
    blank = db.get(SiteContent, SITE_ID)
    if blank is not None:
        db.delete(blank)  # o site foi aberto antes de ligar SEED_DEMO
        db.flush()

    owner = User(
        name="Helena Duarte",
        email=DEMO_OWNER[0],
        role=Role.OWNER,
        password_hash=hash_password(DEMO_OWNER[1], iterations),
    )
    client = User(
        name="Marcos Oliveira",
        email=DEMO_CLIENT[0],
        phone="(19) 98877-6655",
        city="Campinas, SP",
        role=Role.CLIENT,
        password_hash=hash_password(DEMO_CLIENT[1], iterations),
    )
    db.add_all([owner, client])

    db.add(
        SiteContent(
            id=SITE_ID,
            **DEMO_TEXTS,
            hero_image_id=_image(db, "capa-banquete"),
            owner_image_id=_image(db, "retrato-chef"),
            history_image_id=_image(db, "historia-cozinha"),
        )
    )
    db.add_all(
        [
            BioPhoto(
                image_id=_image(db, "mesa-posta"), caption="Cada mesa é montada por nós", position=1
            ),
            BioPhoto(
                image_id=_image(db, "evento-coquetel"), caption="Canapés feitos no dia", position=2
            ),
        ]
    )

    events = [
        (
            "Casamento de Júlia e Rafael",
            "Casamento",
            40,
            180,
            "Chácara em Valinhos, SP",
            "Jantar em quatro tempos com risoto de cogumelos, filé ao molho de vinho e mesa de "
            "doces finos. Bolo de três andares com flores naturais.",
            ["evento-casamento", "mesa-posta", "capa-banquete"],
        ),
        (
            "Coquetel de lançamento",
            "Corporativo",
            75,
            90,
            "Escritório no centro de Campinas",
            "Coquetel volante com 14 tipos de canapés, drinks sem álcool e estação de cafés.",
            ["evento-coquetel", "evento-corporativo"],
        ),
        (
            "15 anos da Lara",
            "15 anos",
            110,
            150,
            "Salão de festas em Campinas",
            "Noite em tons de lilás, buffet completo, mesa de doces e bolo cenográfico.",
            ["evento-15-anos"],
        ),
        (
            "Aniversário de 60 anos do seu Antônio",
            "Aniversário",
            150,
            70,
            "Casa da família, em Sousas",
            "Almoço de família com feijoada completa, caipirinhas e bolo de nozes da receita da "
            "casa.",
            ["evento-aniversario"],
        ),
        (
            "Café da manhã de convenção",
            "Corporativo",
            200,
            250,
            "Centro de convenções",
            "Café da manhã para 250 pessoas, com pães de fermentação natural, frutas, "
            "tapiocas feitas na hora e café especial.",
            ["evento-corporativo"],
        ),
    ]
    for title, kind, days_ago, guests, location, description, photos in events:
        event = Event(
            title=title,
            event_type=kind,
            event_date=today - timedelta(days=days_ago),
            guests=guests,
            location=location,
            description=description,
        )
        event.photos = [
            EventPhoto(image_id=_image(db, name), position=n) for n, name in enumerate(photos)
        ]
        db.add(event)

    db.flush()
    quote = Quote(
        client_id=client.id,
        event_type="Aniversário",
        event_date=today + timedelta(days=45),
        guests=80,
        location="Salão do condomínio, Campinas",
        budget="R$ 10 a 20 mil",
        details="Festa de 40 anos da minha esposa, surpresa. Ela adora comida italiana.",
        status=QuoteStatus.TALKING,
    )
    db.add(quote)
    db.flush()
    conversation = [
        (
            False,
            "Oi, Helena! Vi o portfólio e adorei o casamento da Júlia. Vocês fazem massas na hora?",
        ),
        (
            True,
            "Olá, Marcos! Que bom que gostou. Fazemos sim: temos uma estação de massas "
            "com três molhos, montada na frente dos convidados. Combina muito com festa "
            "surpresa.",
        ),
        (
            True,
            "Para 80 pessoas, consigo te mandar duas opções de cardápio até amanhã. O "
            "salão tem cozinha de apoio?",
        ),
    ]
    for from_owner, body in conversation:
        db.add(
            Message(
                quote_id=quote.id,
                sender_id=owner.id if from_owner else client.id,
                from_owner=from_owner,
                body=body,
            )
        )
    db.flush()
    first = db.scalar(select(Message.id).where(Message.quote_id == quote.id).order_by(Message.id))
    quote.client_read_id = first  # as duas respostas da Helena aparecem como novas
    quote.owner_read_id = first + 2
    _demo_reactions(db)
    _demo_dashboard(db)


def _demo_reactions(db: Session) -> None:
    """Um coração e uma conversa nos comentários, para mostrar como a seção funciona."""
    if db.scalar(select(EventComment.id).limit(1)) is not None:
        return
    owner = db.scalar(select(User).where(User.email == DEMO_OWNER[0]))
    client = db.scalar(select(User).where(User.email == DEMO_CLIENT[0]))
    wedding = db.scalar(select(Event).where(Event.title == "Casamento de Júlia e Rafael"))
    if not (owner and client and wedding):
        return
    db.add(EventLike(event_id=wedding.id, user_id=client.id))
    db.add(
        EventComment(
            event_id=wedding.id,
            user_id=client.id,
            body="Que mesa linda! Vocês montam a decoração de doces também?",
        )
    )
    db.flush()
    db.add(
        EventComment(
            event_id=wedding.id,
            user_id=owner.id,
            body="Obrigada, Marcos! Montamos sim, a mesa de doces é toda feita por nós.",
        )
    )


def _demo_dashboard(db: Session) -> None:
    """Números de exemplo na aba Resultados, tirados da planilha de demonstração."""
    if db.get(Dashboard, 1) is not None:
        return
    data = json.loads((DEMO_DIR / "resultados.json").read_text(encoding="utf-8"))
    db.add(
        Dashboard(
            id=1,
            file_name="Planilha_Buffet_DRE_Estoque.ods (exemplo)",
            data=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        )
    )
