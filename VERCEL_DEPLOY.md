# GeneLink — preparação para deploy na Vercel

O projeto continua sendo Flask + Jinja + PostgreSQL. O arquivo `app.py` na raiz apenas expõe a aplicação existente em `artifacts/api-server/app.py`, permitindo que a Vercel reconheça o Flask sem reescrever as páginas.

## Configuração do projeto

- Root Directory: raiz do repositório
- Runtime Python: 3.12 (fixado em `.python-version`)
- Entrypoint: `app.py`
- Dependências: `pyproject.toml` / `requirements.txt`

## Variáveis obrigatórias na Vercel

Configure em Project Settings → Environment Variables para Production e Preview:

| Variável | Finalidade |
|---|---|
| `DATABASE_URL` | URL PostgreSQL persistente |
| `SESSION_SECRET` | Segredo forte usado para assinar sessões |
| `FIREBASE_API_KEY` | Configuração pública do Firebase Web |
| `FIREBASE_AUTH_DOMAIN` | Domínio de autenticação Firebase |
| `FIREBASE_PROJECT_ID` | ID do projeto Firebase |
| `FIREBASE_STORAGE_BUCKET` | Storage bucket Firebase |
| `FIREBASE_MESSAGING_SENDER_ID` | Sender ID Firebase |
| `FIREBASE_APP_ID` | App ID Firebase |
| `FIREBASE_PRIVATE_KEY` | Chave privada da Service Account Firebase |
| `FIREBASE_CLIENT_EMAIL` | E-mail da Service Account Firebase |

Também são aceitas/configuradas as variáveis opcionais `FIREBASE_PRIVATE_KEY_ID`, `FIREBASE_CLIENT_ID`, `FIREBASE_MEASUREMENT_ID`, `ALLOWED_ORIGINS`, `BASE_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASS`, `RESEND_API_KEY` e `RESEND_FROM`.

**Segredos:** nunca coloque a Service Account JSON, chave privada, senha do banco ou SESSION_SECRET no Git. Em `FIREBASE_PRIVATE_KEY`, preserve as quebras de linha como `\\n` se o painel da Vercel armazenar o valor em uma única linha.

## Banco de dados

A Vercel executa funções serverless; o disco local não deve ser tratado como banco persistente. Use PostgreSQL externo e configure `DATABASE_URL`.

O código verifica a conectividade com PostgreSQL na inicialização da função e não executa `init_db()` automaticamente quando detecta Vercel. Isso evita tentar criar/migrar tabelas em cada inicialização. Se usar o mesmo PostgreSQL já utilizado pelo Render, confirme que todas as tabelas e migrações necessárias já existem antes de direcionar tráfego para a Vercel. Se for um banco novo, execute a inicialização do schema uma única vez em ambiente controlado antes do primeiro deploy.

## Verificação pós-deploy

1. Abra a URL de Preview antes de alterar o domínio de produção.
2. Confira `/gl/api/healthz`: o campo `database` deve retornar `connected`.
3. Teste páginas públicas, login, cadastro, recuperação de senha, pesquisa NCBI, fórum, instituições, parcerias e mensagens.
4. Confira os logs da função durante esses testes.
5. Só depois de validar o fluxo completo, altere o domínio/DNS. Mantenha o serviço Render disponível como rollback até concluir a validação.

## Pontos de atenção antes de produção

- O rate limiter aceita `RATELIMIT_STORAGE_URI` para armazenamento compartilhado (por exemplo, Redis). Sem essa variável, usa memória local; em serverless, instâncias diferentes não compartilham esse estado. O bloqueio customizado de login também permanece em memória e precisa ser movido para armazenamento compartilhado antes de produção ampla.
- O backend abre conexões PostgreSQL diretamente por requisição. Configure o pooler recomendado pelo provedor do banco e acompanhe o limite de conexões.
- Escolha a região da função próxima da região do PostgreSQL para reduzir latência.
- O deploy não migra dados automaticamente: manter o mesmo `DATABASE_URL` preserva os registros; trocar de banco exige migração e validação dos dados.
