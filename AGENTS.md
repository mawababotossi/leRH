# leRH — Process de Développement

## Stack

| Composant | Technologie |
|---|---|
| Core / API | Python 3.11+ / FastAPI |
| Telegram Bot | python-telegram-bot v21+ |
| WhatsApp Bot | Node.js / Baileys |
| AI / LLM | OpenAI API + HuggingFace Transformers |
| Base de données | PostgreSQL + SQLAlchemy + Alembic |
| Cache / Queue | Redis (optionnel) |

## Architecture

```
src/leRH/
├── api/              # REST API FastAPI (coeur métier)
│   ├── routers/
│   └── middleware/
├── core/             # Logique métier (assistants IA, matching, parsing)
│   ├── assistants/
│   ├── documents/    # Génération CV + lettre de motivation (LLM + docx/PDF)
│   ├── matching/
│   └── profiles/
├── db/               # Modèles SQLAlchemy, migrations Alembic
├── adapters/         # Python → Telegram
│   └── telegram/     # Bot handlers, conversation states
├── services/         # Audio, TTS, traduction, parsing CV
├── schemas/          # Pydantic models
└── utils/            # Helpers

adapters/whatsapp/    # Node.js — Baileys (hors src/ Python)
├── package.json
├── src/
│   ├── bot.ts        # WhatsApp bot principal
│   ├── session/      # Auth state Baileys
│   └── api-client.ts # Client HTTP vers API Python
└── tests/
```

## Flow de Développement

### 1. Branches

- `main` — stable, déployable
- `dev` — intégration
- `feat/<nom>` — nouvelle fonctionnalité
- `fix/<nom>` — correctif
- `chore/<nom>` — maintenance (deps, config, CI)

### 2. Commits — Conventional Commits

```
feat: ajout du parsing CV multimodal
fix: correction timeout transcription audio
chore: mise à jour des dépendances
test: couverture des handlers Telegram
docs: méthodologie de développement
refactor: extraction des assistants IA dans core/
```

Types : `feat` `fix` `chore` `test` `docs` `refactor` `perf` `ci` `build`

Format : `<type>: <description en français>`

### 3. Code — Avant chaque commit

```bash
ruff check .        # Lint
ruff format --diff .  # Vérifie le formatage
pytest              # Tests (doivent passer)
```

Le hook `.pre-commit-config.yaml` fait ça automatiquement.

### 4. Qualité

- **Tests obligatoires** sur les nouveaux modules
- **Couverture minimum** : 70% (configuré dans `pyproject.toml`)
- **Type hints** partout — mypy en check optionnel (non bloquant)
- **Docstrings** pour les fonctions publiques (format Google-style)
- **Pas de `print()`** — utiliser `logging`
- **Pas de secrets** hardcodés — utiliser `pydantic-settings` + `.env`

### 5. Tests

```bash
# Tous les tests
pytest

# Un fichier spécifique
pytest tests/test_handlers.py

# Avec watch
pytest -f

# Couverture HTML
pytest --cov=src/leRH --cov-report=html
```

Organisation des tests:
```
tests/
├── conftest.py          # Fixtures partagées
├── test_api/            # Tests API
├── test_core/           # Tests logique métier
├── test_telegram/       # Tests bot Telegram
└── test_services/       # Tests services (audio, tts, etc.)
```

### 6. Review — Checklist avant PR

- [ ] Tests passent localement
- [ ] Ruff sans erreur
- [ ] Pas de secrets ou clés API dans le code
- [ ] Nouvelles dépendances justifiées et dans `pyproject.toml`
- [ ] Breaking changes documentés
- [ ] README mis à jour si nécessaire

### 7. Déploiement

- **Staging** : auto-déploiement depuis `dev`
- **Production** : déploiement manuel depuis `main`
- CI via `.gitlab-ci.yml` (lint → test → build image → deploy)

### 8. Génération de documents (CV + Lettre de motivation)

Endpoints :

| Endpoint | Description |
|---|---|
| `POST /documents/generate-cv` | Génère un CV ATS-optimisé (.docx/.pdf) |
| `POST /documents/generate-cover-letter` | Génère une lettre de motivation (.docx/.pdf) |
| `POST /documents/generate-all` | Génère les deux documents dans un ZIP |

**Body** : `{ "user_id": "...", "job_id": "...", "format": "docx|pdf" }`

**Architecture** :
1. `DocumentGenerator` (LLM) génère le contenu structuré en JSON à partir du profil user + offre
2. Le contenu est rendu en .docx via `python-docx` (template ATS-friendly, Calibri, single column)
3. Le .pdf est généré via `fpdf2` avec la même mise en page
4. Les prompts LLM intègrent les règles ATS (pas d'images, pas d'en-têtes, mots-clés du JD, etc.)

### 9. Système de Crédits

Chaque utilisateur reçoit **20 crédits** à l'inscription. Les actions suivantes consomment des crédits :

| Action | Coût |
|---|---|
| Génération de CV | 5 crédits |
| Génération de lettre de motivation | 3 crédits |
| Notification quotidienne envoyée | 1 crédit |
| Abonnement aux alertes emploi | Gratuit (+7 crédits bonus) |

Les crédits sont gérés par `CreditManager` (`core/credits.py`) avec une base SQLite synchrone pour compatibilité avec les appels d'outils de l'Assistant.

### 10. Assistant IA — Outils disponibles

Koffi dispose de ces outils (function calling) :

| Outil | Description | Condition |
|---|---|---|
| `search_local_jobs` | Cherche dans la DB locale | Disponible si `local_jobs` fourni |
| `search_web_jobs` | Cherche sur le web (DuckDuckGo) | Toujours disponible |
| `generate_cv` | Génère un CV ATS pour une offre | 5 crédits, nécessite `user_id` |
| `generate_cover_letter` | Génère une lettre de motivation | 3 crédits, nécessite `user_id` |
| `subscribe_job_alerts` | Active les alertes quotidiennes | Gratuit, donne 7 crédits bonus |

Le `user_id` et `credits` sont passés à l'Assistant depuis les handlers (Telegram/WhatsApp).

## Commandes rapides

```bash
# Installer les dépendances
pip install -e ".[dev]"

# Installer pre-commit
pre-commit install

# Lancer l'API en dev
uvicorn leRH.api.app:app --reload

# Lancer le bot Telegram
python -m leRH.adapters.telegram.bot

# Lancer le bot WhatsApp (depuis adapters/whatsapp)
npm run dev

# Générer une migration Alembic
alembic revision --autogenerate -m "description"

# Appliquer les migrations
alembic upgrade head
```
