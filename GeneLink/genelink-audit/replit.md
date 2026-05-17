# GeneLink

Plataforma científica real de pesquisa genética — conecta pesquisadores com dados genômicos reais do NCBI, fórum colaborativo e chat em tempo real.

## Run & Operate

- `python artifacts/api-server/app.py` — inicia o servidor Flask (porta 8080)
- `pip install -r artifacts/api-server/requirements.txt` — instala dependências Python
- Required env: `DATABASE_URL`, `SESSION_SECRET` — PostgreSQL e chave JWT

## Stack

- **Backend**: Python 3.11 · Flask · Flask-SocketIO · psycopg2 · bcrypt · PyJWT
- **Frontend**: HTML5 · CSS3 · JavaScript puro (sem frameworks SPA)
- **Banco de dados**: PostgreSQL (Drizzle removido — schema direto via psycopg2)
- **Tempo real**: WebSocket via Flask-SocketIO + Socket.IO (cliente CDN)
- **API externa**: NCBI Entrez eutils (eutils.ncbi.nlm.nih.gov) — dados reais de genes

## Where things live

- `artifacts/api-server/app.py` — aplicação Flask principal (rotas + SocketIO + inicialização)
- `artifacts/api-server/routes/auth.py` — registro, login, JWT, perfil de usuário
- `artifacts/api-server/routes/genes.py` — busca NCBI (esearch + esummary)
- `artifacts/api-server/routes/forum.py` — posts e comentários da comunidade
- `artifacts/api-server/db/init_db.py` — schema PostgreSQL e inicialização automática
- `artifacts/api-server/db/connection.py` — conexão com banco de dados
- `artifacts/api-server/templates/` — 7 páginas HTML independentes
- `artifacts/api-server/static/css/main.css` — estilos globais (design acadêmico/científico)
- `artifacts/api-server/static/js/api.js` — utilitários de API compartilhados + navbar dinâmica
- `lib/api-spec/openapi.yaml` — spec Node.js original (não usado pelo Flask)

## Páginas

| URL | Arquivo | Descrição |
|-----|---------|-----------|
| `/` | `index.html` | Landing page institucional |
| `/login` | `login.html` | Login e cadastro com abas |
| `/dashboard` | `dashboard.html` | Painel principal do pesquisador |
| `/search` | `search.html` | Busca de genes via NCBI real |
| `/profile` | `profile.html` | Perfil editável do pesquisador |
| `/forum` | `forum.html` | Fórum científico com posts |
| `/forum/<id>` | `forum_post.html` | Post individual com comentários |
| `/chat` | `chat.html` | Chat global em tempo real |

## API Routes

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/register` | Cadastro de usuário (bcrypt) |
| POST | `/api/login` | Login com JWT (7 dias) |
| GET | `/api/user` | Dados do usuário autenticado |
| PUT | `/api/user/profile` | Atualizar perfil |
| GET | `/api/search-gene?q=` | Busca NCBI Gene (real) |
| GET | `/api/search-history` | Histórico de buscas do usuário |
| GET | `/api/posts` | Listar posts do fórum |
| GET | `/api/posts/<id>` | Post + comentários |
| POST | `/api/posts` | Criar novo post |
| POST | `/api/posts/<id>/comments` | Comentar post |
| DELETE | `/api/posts/<id>` | Deletar post (apenas autor) |
| GET | `/api/categories` | Categorias científicas |
| WS | `/socket.io` | Chat em tempo real |

## Architecture decisions

- Flask serve TANTO a API REST quanto os arquivos HTML (templates Jinja2) — um único serviço
- JWT armazenado em `localStorage`, enviado como `Bearer` header em todas as chamadas de API
- WebSocket gerenciado pelo Flask-SocketIO com eventlet (async_mode)
- Banco de dados inicializado automaticamente via `init_db()` na startup do Flask
- NCBI Entrez chamado em tempo real — nenhum dado simulado ou mockado
- Autenticação protege todas as rotas de API (exceto GET /posts e /categories)

## Product

GeneLink é uma plataforma científica completa para:
- Busca de genes reais via NCBI (BRCA1, TP53, EGFR, etc.)
- Comunidade de pesquisadores com fórum e posts categorizados
- Chat global em tempo real para colaboração científica
- Perfis de pesquisadores com afiliação institucional e área de pesquisa
- Dashboard com histórico de buscas e atividade da comunidade

## GitHub

Para conectar ao GitHub, adicione `GITHUB_TOKEN` (Personal Access Token com permissão `repo`) nos secrets do Replit. O token permite criar o repositório e fazer push automaticamente.

Manualmente:
```bash
git remote add origin https://github.com/<seu-usuario>/GeneLink.git
git push -u origin main
```

## Gotchas

- Flask-SocketIO requer `eventlet` instalado — está em `requirements.txt`
- O Socket.IO client é carregado via CDN no `chat.html` — versão 4.7.5
- `DATABASE_URL` é obrigatório — fornecido automaticamente pelo Replit PostgreSQL
- Rodar `pip install -r requirements.txt` antes de iniciar se as dependências mudarem
- O servidor Flask inicializa o banco automaticamente — não precisa rodar migrations manualmente
