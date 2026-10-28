# Site de Buffet

Site completo para um buffet: apresentação da dona e da história da empresa, portfólio de
eventos com fotos, área do cliente e **pedido de orçamento que vira uma conversa** entre o
cliente e o buffet, tudo guardado no próprio site. A dona edita textos, fotos e portfólio por
um painel, sem mexer em código.

Feito com **FastAPI**, **SQLAlchemy 2** e **PostgreSQL**, com a interface em JavaScript puro
servida pela própria API.

> O conteúdo de exemplo ("Buffet Alecrim", "Helena Duarte") é fictício e as fotos são
> ilustrações. No site de verdade, tudo é trocado pelo painel.

![Página inicial](docs/inicio.png)

## O que o site faz

**Para os visitantes**
- **Apresentação**: capa com foto, seção *Sobre mim* (foto, biografia e mais fotos) e
  *Nossa história* (como a empresa foi fundada, com ano de fundação e foto).
- **Portfólio**: eventos com várias fotos, filtro por tipo (casamento, 15 anos, corporativo…),
  página de cada evento e visualização ampliada das fotos (setas do teclado funcionam).
- Botão **Agendar evento** sempre à vista: leva ao pedido de orçamento.

**Para os clientes**
- **Cadastro** com nome, e-mail, telefone/WhatsApp e cidade. Quem clica em *Agendar evento*
  sem conta cria a conta e volta direto para o pedido.
- **Pedido de orçamento**: tipo de evento, data, convidados, local, faixa de investimento e
  detalhes. O pedido abre uma **conversa** com o buffet.
- **Minha conta**: lista de pedidos com situação e aviso de mensagens novas.

**Para a dona do buffet (painel)**
- **Orçamentos**: caixa de entrada com busca e filtro por situação (novo, em conversa,
  proposta enviada, fechado, não fechado), conversa ao lado e **ficha do cliente** com
  e-mail, telefone (com atalho para o WhatsApp), cidade e data de cadastro.
- **Portfólio**: publicar, editar e excluir eventos; enviar várias fotos de uma vez
  (arrastando), reordenar e escolher a capa.
- **Textos e fotos do site**: capa, biografia, história, contato e todas as fotos.
- **Clientes**: todos os cadastrados, com contato e quantidade de pedidos.

| Sobre mim | Portfólio |
|---|---|
| ![Sobre mim](docs/sobre.png) | ![Portfólio](docs/portfolio.png) |
| **Conversa do orçamento (cliente)** | **Painel: orçamentos e ficha do cliente** |
| ![Conversa](docs/conversa.png) | ![Painel](docs/painel.png) |
| **Painel: textos e fotos** | **No celular** |
| ![Painel do site](docs/painel-site.png) | ![Celular](docs/celular.png) |

## Detalhes técnicos

| Tema | Como aparece no código |
|---|---|
| API REST | FastAPI com validação Pydantic, erros em português campo a campo, OpenAPI em `/docs` |
| Banco | SQLAlchemy 2 (ORM tipado), SQLite no desenvolvimento e PostgreSQL em produção |
| Fotos | Guardadas no banco (sobrevivem a novos deploys). Toda foto é reaberta pelo Pillow: só entra imagem de verdade, o tamanho cai para no máximo 1920 px e os dados de GPS/EXIF do celular são removidos. Cache de um ano no navegador |
| Conversa | Mensagens novas por consulta a cada 4 s (`?after=`), sem WebSocket: funciona em qualquer hospedagem. Contagem de não lidas por id da última mensagem lida |
| Segurança | Senhas com PBKDF2 + sal, JWT, limite de tentativas de login, cada cliente só vê os próprios pedidos (pedido alheio responde 404), cadastro nunca cria administrador, cabeçalhos CSP / nosniff / frame-ancestors |
| Qualidade | 46 testes com pytest rodando no SQLite **e no PostgreSQL** a cada push (GitHub Actions), Ruff |
| Entrega | Docker e Blueprint do Render (`render.yaml` com PostgreSQL; `render-demo.yaml` para demonstração) |

```
app/
├── main.py           # monta a aplicação, cabeçalhos de segurança, site em /
├── models.py         # tabelas: usuários, conteúdo, fotos, eventos, pedidos, mensagens
├── schemas.py        # validação de entrada e formato de saída
├── images.py         # tratamento das fotos enviadas (Pillow)
├── routers/          # auth, site, portfolio, quotes
├── seed.py           # conta da administração e site de demonstração
└── static/           # interface (HTML, CSS e JavaScript puro)
```

## Rodar no computador

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
SEED_DEMO=true uvicorn app.main:app --reload       # http://127.0.0.1:8000
```

Com `SEED_DEMO=true`, a tela de entrada oferece as contas de exemplo:

| Conta | E-mail | Senha |
|---|---|---|
| Cliente | `marcos@cliente.dev` | `demo12345` |
| Administração | `helena@buffet.dev` | `demo12345` |

Testes: `pytest` (ou, contra PostgreSQL, `TEST_DATABASE_URL=postgresql://... pytest`).

## Publicar

### Site de verdade (dados permanentes)

1. No [Render](https://render.com): **New → Blueprint** e escolha este repositório (usa o
   `render.yaml`, que cria o site e um PostgreSQL).
2. Preencha `OWNER_EMAIL`, `OWNER_PASSWORD` (mínimo 8 caracteres) e `OWNER_NAME`: é o login
   da dona do buffet. A conta é criada ao iniciar o servidor.
3. Entre no site com esse e-mail e use o **Painel** para trocar textos, fotos e portfólio.

O PostgreSQL gratuito do Render expira em 30 dias; para um cliente real, use o plano pago
mais barato do banco (ou outro PostgreSQL, informando `DATABASE_URL`).

### Demonstração

Use o `render-demo.yaml` (**New → Blueprint**, apontando para esse arquivo). Ele sobe o site de
exemplo num SQLite interno, que volta ao exemplo sempre que o servidor reinicia.

### Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `DATABASE_URL` | PostgreSQL (`postgres://...`). Sem ela, usa SQLite local |
| `SECRET_KEY` | Assina os logins. Obrigatória em produção |
| `OWNER_EMAIL`, `OWNER_PASSWORD`, `OWNER_NAME` | Conta da administração |
| `SEED_DEMO` | `true` preenche o site de exemplo (só com o banco vazio) |
| `MAX_UPLOAD_MB` | Tamanho máximo de cada foto enviada (padrão 10) |

## Licença

MIT
