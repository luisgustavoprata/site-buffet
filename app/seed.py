"""Conta da administração e conteúdo de demonstração.

- `ensure_owner`: cria a conta da dona do buffet a partir de OWNER_EMAIL e OWNER_PASSWORD.
- `seed_demo`: preenche um site de exemplo (textos, ilustrações, portfólio, um cliente e uma
  conversa) para quem quer conhecer o projeto. Só roda com o banco vazio.
"""

from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.images import process_upload
from app.models import (
    BioPhoto,
    Event,
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


def seed_demo(db: Session, today: date, iterations: int) -> None:
    if db.get(SiteContent, SITE_ID) is not None:
        return  # já tem conteúdo: reiniciar o servidor não duplica nada

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
            business_name="Buffet Alecrim",
            tagline="Comida feita em casa para os dias mais importantes",
            hero_title="Sua festa com sabor de casa de vó, e serviço de restaurante.",
            hero_text=(
                "Casamentos, aniversários e eventos de empresa com cardápio feito para "
                "você, do primeiro canapé ao último cafezinho."
            ),
            owner_name="Helena Duarte",
            owner_role="Chef e fundadora",
            bio=(
                "Cresci na cozinha da minha avó, em Minas Gerais, ajudando a abrir massa de "
                "pão de queijo antes de saber escrever o meu nome. Foi lá que aprendi que "
                "comida boa é a que faz as pessoas ficarem mais um pouco à mesa.\n\n"
                "Me formei em Gastronomia, trabalhei oito anos em restaurantes e cozinhas de "
                "hotel e, em cada evento, pensava em como seria servir aquela comida com o "
                "carinho de casa. Hoje cuido pessoalmente de cada cardápio: converso com você, "
                "provo junto e acompanho a festa do início ao fim."
            ),
            history_title="Como o Alecrim começou",
            history=(
                "O Alecrim nasceu em 2014, num casamento de uma amiga. O buffet contratado "
                "cancelou na última semana e eu me ofereci para cozinhar para 120 convidados "
                "com a ajuda da minha mãe e de duas primas.\n\n"
                "No fim da noite, três pessoas pediram o meu telefone. No mês seguinte vieram "
                "mais seis. A cozinha de casa ficou pequena, alugamos o primeiro espaço e o "
                "nome veio do vaso de alecrim que nunca saiu da janela.\n\n"
                "Hoje somos uma equipe de 18 pessoas e já servimos mais de 600 eventos, sem "
                "abrir mão do que nos trouxe até aqui: ingrediente fresco, receita de família "
                "e atenção a cada detalhe."
            ),
            founded_year=2014,
            city="Campinas, SP",
            phone="(19) 3200-0000",
            email="contato@buffetalecrim.dev",
            instagram="buffetalecrim",
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
