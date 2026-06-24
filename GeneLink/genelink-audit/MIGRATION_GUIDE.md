# GeneLink — Guia de Migração para Firebase Auth + PostgreSQL

## Visão Geral da Nova Arquitetura

```
ANTES                              DEPOIS
─────────────────────────────────  ──────────────────────────────────────────
SQLite ou PostgreSQL               PostgreSQL (dados estruturados)
  └── usuarios com senha_hash        └── users com firebase_uid (sem senha)
  └── chat_messages (SQL)            └── posts, forum, institutions, preprints
  └── channel_messages (SQL)
  └── private_messages (SQL)       Firebase Auth
JWT manual (PyJWT + bcrypt)          └── autenticação de email/senha
                                     └── login social (Google, etc.)
                                     └── renovação automática de tokens

                                   Firebase Firestore (mensagens em tempo real)
                                     └── chat_messages/{id}
                                     └── channel_messages/{channel_id}/messages/{id}
                                     └── dm_conversations/{conv_id}/messages/{id}
```

---

## PARTE 1 — Configurar o Firebase

### 1.1 Criar projeto no Firebase Console

1. Acesse [console.firebase.google.com](https://console.firebase.google.com)
2. Clique em **Adicionar projeto**
3. Nome do projeto: `GeneLink` (ou qualquer nome)
4. Desative o Google Analytics (opcional)
5. Clique em **Criar projeto**

### 1.2 Ativar Authentication

1. No menu lateral, vá em **Authentication** → **Começar**
2. Na aba **Sign-in method**, ative:
   - **E-mail/senha** → Ativar
   - **Google** → Ativar (opcional, mas recomendado)
3. Na aba **Settings** → **Authorized domains**, adicione seu domínio de produção

### 1.3 Ativar Firestore

1. No menu lateral, vá em **Firestore Database** → **Criar banco de dados**
2. Escolha **Começar no modo de produção**
3. Selecione a região mais próxima do servidor (ex: `southamerica-east1` para Brasil)
4. Clique em **Criar**

### 1.4 Configurar regras do Firestore

No Firestore Console → **Regras**, substitua pelo seguinte:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Chat global: qualquer usuário autenticado pode ler e escrever
    match /chat_messages/{messageId} {
      allow read: if request.auth != null;
      allow create: if request.auth != null
                    && request.resource.data.user_id is int
                    && request.resource.data.message.size() <= 2000;
      allow update, delete: if false;
    }

    // Mensagens de canais
    match /channel_messages/{channelId}/messages/{messageId} {
      allow read: if request.auth != null;
      allow create: if request.auth != null;
      allow update, delete: if false;
    }

    // Mensagens diretas (DMs)
    match /dm_conversations/{convId}/messages/{messageId} {
      allow read: if request.auth != null;
      allow create: if request.auth != null
                    && request.resource.data.content.size() <= 4000;
      allow update, delete: if false;
    }
  }
}
```

### 1.5 Gerar credenciais do servidor (Service Account)

1. No Firebase Console → **Configurações do projeto** (ícone de engrenagem)
2. Aba **Contas de serviço**
3. Clique em **Gerar nova chave privada**
4. Salve o arquivo JSON gerado como `firebase-service-account.json`
5. **NUNCA faça commit deste arquivo** — adicione ao `.gitignore`

---

## PARTE 2 — Configurar Variáveis de Ambiente

Crie ou atualize seu arquivo `.env` (ou configure no servidor):

```env
# PostgreSQL — banco de dados principal
DATABASE_URL=postgresql://usuario:senha@host:5432/genelink

# Flask session secret (mantenha o mesmo valor)
SESSION_SECRET=seu_secret_aqui

# Firebase — credenciais do servidor (escolha uma opção):
# Opção A: caminho para o arquivo JSON (local/dev)
FIREBASE_SERVICE_ACCOUNT_PATH=firebase-service-account.json

# Opção B: conteúdo JSON como string (produção/CI)
# FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}
```

### Para configurar no Render.com:

1. Vá em **Environment** → **Add Environment Variable**
2. Adicione `DATABASE_URL` com a string de conexão PostgreSQL
3. Adicione `FIREBASE_SERVICE_ACCOUNT_JSON` com o conteúdo JSON do service account
4. Adicione `SESSION_SECRET` com um valor seguro

---

## PARTE 3 — Instalar Dependências

```bash
pip install -r requirements.txt
```

O `requirements.txt` agora inclui:
```
firebase-admin==6.5.0
```

As dependências removidas (não precisam mais):
- ~~`bcrypt`~~ — Firebase gerencia senhas
- ~~`PyJWT`~~ — Firebase emite e valida tokens

---

## PARTE 4 — Migrar o Banco de Dados

### 4.1 Rodar script de migração SQL

Execute o arquivo `db/migration_to_firebase_sql.sql` no seu PostgreSQL:

```bash
psql $DATABASE_URL -f db/migration_to_firebase_sql.sql
```

Isso adiciona a coluna `firebase_uid` nas tabelas `users` e `institutions`.

### 4.2 Migrar usuários existentes para Firebase Auth

Para cada usuário existente no banco, você precisa criar um usuário no Firebase
e salvar o `uid` de volta no banco.

**Script de migração de usuários** (rode uma vez):

```python
# scripts/migrate_users_to_firebase.py
import os
import psycopg2
import psycopg2.extras
import firebase_admin
from firebase_admin import credentials, auth

# Inicializa Firebase Admin
cred = credentials.Certificate("firebase-service-account.json")
firebase_admin.initialize_app(cred)

conn = psycopg2.connect(os.environ["DATABASE_URL"],
                        cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()
cur.execute("SELECT id, email, username, password_hash FROM users WHERE firebase_uid IS NULL")
users = cur.fetchall()

migrated = 0
for user in users:
    try:
        # Cria o usuário no Firebase (sem senha — ele precisará resetar)
        firebase_user = auth.create_user(
            email=user["email"],
            display_name=user["username"],
            # Nota: não é possível migrar senhas bcrypt para Firebase
            # O usuário receberá um email de reset de senha
        )
        # Atualiza o banco com o firebase_uid
        cur.execute(
            "UPDATE users SET firebase_uid = %s WHERE id = %s",
            (firebase_user.uid, user["id"])
        )
        migrated += 1
        print(f"✓ Migrado: {user['email']} → {firebase_user.uid}")
    except Exception as e:
        print(f"✗ Erro ao migrar {user['email']}: {e}")

conn.commit()
cur.close()
conn.close()
print(f"\n{migrated}/{len(users)} usuários migrados.")
print("Envie um email de reset de senha para todos os usuários migrados.")
```

### 4.3 Enviar emails de reset de senha

Após migrar, envie emails de reset para todos os usuários:

```python
# scripts/send_password_reset.py
import firebase_admin
from firebase_admin import credentials, auth
import psycopg2
import psycopg2.extras
import os

cred = credentials.Certificate("firebase-service-account.json")
firebase_admin.initialize_app(cred)

conn = psycopg2.connect(os.environ["DATABASE_URL"],
                        cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()
cur.execute("SELECT email FROM users WHERE firebase_uid IS NOT NULL")
users = cur.fetchall()

for user in users:
    link = auth.generate_password_reset_link(user["email"])
    print(f"Reset link para {user['email']}: {link}")
    # Aqui você enviaria o email com seu serviço de email

cur.close()
conn.close()
```

---

## PARTE 5 — Atualizar o Frontend

### 5.1 Adicionar Firebase SDK ao HTML

Adicione no `<head>` de todos os templates HTML:

```html
<!-- Firebase SDK (via CDN) -->
<script type="module">
  import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js';
  import { getAuth } from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js';
  import { getFirestore } from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js';

  const firebaseConfig = {
    apiKey: "COLE_AQUI",
    authDomain: "COLE_AQUI.firebaseapp.com",
    projectId: "COLE_AQUI",
    storageBucket: "COLE_AQUI.appspot.com",
    messagingSenderId: "COLE_AQUI",
    appId: "COLE_AQUI"
  };

  window.firebaseApp = initializeApp(firebaseConfig);
  window.firebaseAuth = getAuth(window.firebaseApp);
  window.firebaseDb = getFirestore(window.firebaseApp);
</script>
```

### 5.2 Substituir auth.js pelo novo auth_firebase.js

Substitua nos templates:
```html
<!-- ANTES -->
<script src="/gl/static/js/auth.js"></script>

<!-- DEPOIS -->
<script type="module" src="/gl/static/js/auth_firebase.js"></script>
```

### 5.3 Atualizar chamadas de API

**ANTES (JWT manual):**
```javascript
const token = localStorage.getItem("gl_token");
const res = await fetch("/gl/api/user", {
  headers: { Authorization: `Bearer ${token}` }
});
```

**DEPOIS (Firebase token):**
```javascript
import { getIdToken, apiRequest } from "./auth_firebase.js";

// Forma simples usando a função utilitária:
const user = await apiRequest("/user");

// Ou manualmente:
const token = await getIdToken();
const res = await fetch("/gl/api/user", {
  headers: { Authorization: `Bearer ${token}` }
});
```

### 5.4 Chat em tempo real com Firestore

Substitua o polling por listeners em tempo real:

```javascript
// ANTES (polling a cada 3 segundos):
setInterval(() => fetchMessages(), 3000);

// DEPOIS (tempo real com Firestore):
import { collection, onSnapshot, orderBy, query, limit }
  from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js';

const db = window.firebaseDb;
const q = query(
  collection(db, "chat_messages"),
  orderBy("created_at", "asc"),
  limit(100)
);

const unsubscribe = onSnapshot(q, (snapshot) => {
  snapshot.docChanges().forEach((change) => {
    if (change.type === "added") {
      const msg = { id: change.doc.id, ...change.doc.data() };
      renderMessage(msg); // sua função de renderização
    }
  });
});

// Para parar de ouvir:
// unsubscribe();
```

---

## PARTE 6 — Estrutura Final dos Arquivos Alterados

```
artifacts/api-server/
├── app.py                          ← Atualizado: usa chat_firestore e dm_firestore
├── requirements.txt                ← Atualizado: adicionado firebase-admin
│
├── firebase/
│   ├── __init__.py                 ← NOVO
│   └── client.py                   ← NOVO: inicialização do Firebase Admin SDK
│
├── db/
│   ├── connection.py               ← Simplificado: apenas PostgreSQL
│   ├── init_db.py                  ← Atualizado: sem password_hash, com firebase_uid
│   └── migration_to_firebase_sql.sql  ← NOVO: script SQL de migração
│
├── routes/
│   ├── auth.py                     ← Atualizado: usa Firebase ao invés de JWT/bcrypt
│   ├── inst_auth.py                ← Atualizado: usa Firebase ao invés de JWT/bcrypt
│   ├── channels.py                 ← Atualizado: mensagens vão para Firestore
│   ├── chat_firestore.py           ← NOVO: substitui /api/chat/messages do app.py
│   └── dm_firestore.py             ← NOVO: substitui routes/dm.py com Firestore
│
└── static/js/
    └── auth_firebase.js            ← NOVO: substitui auth.js no frontend
```

---

## PARTE 7 — Tabelas que Permanecem no PostgreSQL

| Tabela | O que armazena |
|--------|----------------|
| `users` | Perfis de pesquisadores (com firebase_uid) |
| `institutions` | Dados das instituições |
| `institution_members` | Membros de cada instituição |
| `institution_channels` | Metadados dos canais (nome, permissões) |
| `posts` | Posts do fórum |
| `comments` | Comentários nos posts |
| `gene_searches` | Histórico de buscas de genes |
| `partnerships` | Vagas e parcerias de pesquisa |
| `partnership_applications` | Candidaturas a vagas |
| `research_library` | Biblioteca de recursos |
| `preprints` | Artigos preliminares |
| `preprint_reviews` | Revisões dos preprints |
| `admin_flags` | Denúncias para moderação |

## Coleções que Vão para o Firestore

| Coleção Firestore | O que armazena |
|-------------------|----------------|
| `chat_messages/{id}` | Chat global em tempo real |
| `channel_messages/{channelId}/messages/{id}` | Mensagens dos canais |
| `dm_conversations/{convId}/messages/{id}` | Mensagens diretas privadas |

---

## PARTE 8 — Checklist de Deploy

- [ ] Projeto Firebase criado
- [ ] Authentication ativado (email/senha + Google)
- [ ] Firestore criado com regras de segurança
- [ ] Service Account JSON gerado e configurado no servidor
- [ ] `DATABASE_URL` configurado (PostgreSQL)
- [ ] `FIREBASE_SERVICE_ACCOUNT_JSON` configurado no servidor
- [ ] Script de migração SQL executado
- [ ] Usuários migrados para Firebase Auth
- [ ] Emails de reset de senha enviados
- [ ] Frontend atualizado com Firebase SDK
- [ ] Polling de chat substituído por listeners Firestore
- [ ] Testes de login/registro no novo fluxo
- [ ] Testes de chat em tempo real
- [ ] Backup do banco antes de remover colunas de senha

---

## Perguntas Frequentes

**P: O que acontece com as senhas dos usuários atuais?**
R: As senhas bcrypt não podem ser migradas para o Firebase. Os usuários precisam
   criar uma nova senha via "Esqueci minha senha". Envie emails explicativos antes.

**P: Posso continuar usando SQLite no desenvolvimento?**
R: Não — a nova arquitetura usa apenas PostgreSQL. Use um PostgreSQL local
   (Docker ou Neon.tech tem free tier) para desenvolvimento.

**P: O que acontece com as mensagens antigas do chat?**
R: Elas ficam no PostgreSQL até você exportar para o Firestore manualmente.
   As tabelas `chat_messages`, `channel_messages` e `private_messages` só devem
   ser removidas após a exportação.

**P: Como exportar mensagens antigas para o Firestore?**
R: Use o Firebase Admin SDK no Python para escrever no Firestore em lote.
   Consulte a documentação: https://firebase.google.com/docs/firestore/manage-data/add-data#python
