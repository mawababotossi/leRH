# leRH — Bot de Recrutement Multi-Canal

Plateforme de mise en relation emploi pour le Togo, accessible via **Telegram** et **WhatsApp**.

> *"L'Afrique n'est pas pauvre, elle est mal optimisée."* — Principe n°2

## Canaux

| Canal | Technologie | Statut |
|---|---|---|
| Telegram | python-telegram-bot | En développement |
| WhatsApp | Node.js / Baileys | En développement |

## Architecture

```
[Telegram] ────┐
               ├── Python / FastAPI ─── PostgreSQL
[WhatsApp] ────┘
```

- **API** (FastAPI) : coeur métier, assistants IA, matching
- **Adapters** : Telegram (Python) + WhatsApp (Node.js/Baileys)
- **DB** : PostgreSQL + SQLAlchemy + Alembic

## Démarrage rapide

```bash
# Installer les dépendances Python
pip install -e ".[dev]"

# Pré-commit
pre-commit install

# Lancer l'API
uvicorn leRH.api.app:app --reload

# Lancer le bot Telegram
python -m leRH.adapters.telegram.bot

# Lancer le bot WhatsApp
cd adapters/whatsapp && npm install && npm run dev
```

## Développement

Voir [AGENTS.md](./AGENTS.md) pour la méthodologie complète.

## Documentation produit

Voir le dossier [docs/](./docs/) pour la vision, le modèle économique, et les principes de conception.

## Stack

| Composant | Technologie |
|---|---|
| Core API | Python 3.11+ / FastAPI |
| Telegram Bot | python-telegram-bot |
| WhatsApp Bot | Node.js / Baileys |
| LLM | OpenAI API + HuggingFace |
| DB | PostgreSQL + SQLAlchemy |
| Qualité | Ruff, Pytest, Pre-commit |
