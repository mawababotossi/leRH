# Brainstorming : Système Automatisé IA + WhatsApp/Télégram pour l'Emploi au Togo

## Philosophie : Voice-First, Zero Paper, 100% Automatisé

Le système doit marcher **sans intervention humaine** — même pour un candidat qui ne sait ni lire ni écrire.

---

## Architecture Technique

```
┌─────────────────────────────────────────────────────┐
│                  INTERFACE LAYER                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ WhatsApp Bot  │  │ Telegram Bot │  │  Voice AI │ │
│  │ (Twilio/Meta) │  │ (Telegram API)│  │  (VAPI)   │ │
│  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘ │
└─────────┼──────────────────┼────────────────┼────────┘
          │                  │                │
┌─────────┼──────────────────┼────────────────┼────────┐
│         ▼                  ▼                ▼         │
│                 INTELLIGENCE LAYER                     │
│  ┌──────────────────────────────────────────────┐    │
│  │           AI Orchestrator (LangChain)         │    │
│  │  ┌──────┐ ┌──────┐ ┌───────┐ ┌──────────┐  │    │
│  │  │ CV   │ │Voice │ │Matching│ │Verifica- │  │    │
│  │  │Parser│ │→Text │ │Engine │ │tion Engine│  │    │
│  │  └──────┘ └──────┘ └───────┘ └──────────┘  │    │
│  │  ┌──────┐ ┌──────┐ ┌───────┐ ┌──────────┐  │    │
│  │  │Quiz  │ │Escrow│ │Fraud  │ │ Analytics│  │    │
│  │  │Bot   │ │Logic │ │Detect │ │ (Reports) │  │    │
│  │  └──────┘ └──────┘ └───────┘ └──────────┘  │    │
│  └──────────────────────────────────────────────┘    │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────┼──────────────────────────────┐
│                       ▼                               │
│                   DATA LAYER                          │
│  ┌───────────┐  ┌──────────┐  ┌───────────────────┐ │
│  │ PostgreSQL│  │ pgvector │  │  Object Storage   │ │
│  │ (profiles,│  │(embeddings│  │  (CVs PDF/Images) │ │
│  │  jobs,    │  │ matching)│  │                   │ │
│  │  txns)    │  │          │  │                   │ │
│  └───────────┘  └──────────┘  └───────────────────┘ │
│                                                       │
│  ┌──────────────────────────────────────────────┐    │
│  │           PAYMENT LAYER                        │    │
│  │  Flooz API  |  T-money API  |  CinetPay       │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

### Stack Suggestion

| Composant | Technologie | Coût |
|---|---|---|
| Bot WhatsApp | Meta Cloud API (gratuit) + Twilio ou WATI | ~$0/mois (gratuit jusqu'à 1k conversations) |
| Bot Telegram | Telegram Bot API | Gratuit |
| Voice IA | Whisper (OpenAI API) + VAPI.ai ou Deepgram | ~$0.006/min audio |
| LLM | GPT-4o-mini ou Claude Haiku | ~$0.15-0.40/1M tokens |
| Base de données | Supabase (PostgreSQL + pgvector) | ~$25/mois |
| Hébergement | Railway / Render / Fly.io | ~$20/mois |
| Mobile Money | CinetPay (agrège Flooz + T-money) | ~1.5% par transaction |
| Embeddings | text-embedding-3-small (OpenAI) | ~$0.02/1M tokens |

**Coût total estimé par utilisateur actif** : < 50 FCFA/mois

---

## Parcours Utilisateur Détaillé

### 👤 Candidat — Parcours Voice-First

#### Étape 1 — Découverte
> Le candidat voit un lien WhatsApp sur Facebook.
> Il clique → "Bonjour, bienvenue sur Talents Togo Bot 🤖"

#### Étape 2 — Profil Vocal
```
Bot : "Envoie-moi un message vocal pour te présenter. 
       Dis-moi ton nom, où tu habites, ce que tu sais faire."
👤 : [Message vocal de 30 secondes]
Bot : [Whisper transcrit → LLM extrait les infos]
      "Je vois que tu t'appelles Kossi, tu es à Lomé, 
       tu as 3 ans d'expérience en vente. C'est bien ça ?"
👤 : "Oui c'est ça."
Bot : "Quel est ton dernier diplôme ?"
👤 : [Texte ou vocal] "BAC G2"
Bot : ✅ Profil créé !
```

#### Étape 3 — Vérification Automatique
```
Bot : "Je peux vérifier ton profil en 2 minutes. 
       Ça te permet d'être payé plus vite et d'être 
       prioritaire chez les recruteurs. 
       Envoie 'OUI' pour commencer."
👤 : "OUI"

--- Test de compétences ---
Bot : "Tu as dit que tu sais faire de la vente. 
       Question : Un client veut baisser le prix de 20%, 
       mais ta marge max est de 15%. Que fais-tu ?"
👤 : [Vocal ou texte]
Bot : [LLM évalue la réponse]
      "✓ Compétence vente : 7/10"

--- Vérification Référence (automatisée) ---
Bot : "Donne-moi le numéro de ton ancien employeur, 
       je l'appelle pour confirmer."
👤 : "90 12 34 56"
Bot : [Appelle via VAPI.ai → Pose 3 questions → 
      Transcrit → Analyse le ton, la sincérité]
      "✓ Référence vérifiée"
```

#### Étape 4 — Matching Quotidien
```
Bot : "Bonjour Kossi ! 🎯 
       3 offres correspondent à ton profil aujourd'hui :

       1. Vendeur en boutique — Lomé — 120 000 FCFA/mois
       2. Commercial terrain — Kara — 100 000 FCFA/mois + primes
       3. Téléconseiller — À distance — 80 000 FCFA/mois

       Réponds avec le NUMERO de l'offre pour postuler."
```

#### Étape 5 — Application + Pré-screening
```
👤 : "1"
Bot : "Tu postules chez 'ShopPlus Lomé'. 
       Je vais te poser 3 questions rapides pour le recruteur."

[Questions IA générées dynamiquement selon le poste]
Bot : Q1: "As-tu déjà utilisé un logiciel de caisse ?"
      Q2: "Peux-tu travailler le samedi ?"
      Q3: "Quel est ton préavis ?"

[Les réponses sont analysées par LLM → résumé pour recruteur]
Bot : ✅ Candidature envoyée ! Le recruteur te répond sous 48h.
```

#### Étape 6 — Embauche + Escrow Automatique
```
Bot : "Félicitations ! ShopPlus veut t'embaucher 🎉
       Salaire : 120 000 FCFA/mois
       Début : 1er juin

       Le recruteur dépose 120 000 FCFA sur mon système.
       Tu recevras 114 000 FCFA après 15 jours (commission 5%).
       Tu confirmes ? (OUI/NON)"
👤 : "OUI"
Bot : ✅ Escrow activé. Ton salaire est garanti.
```

---

### 🏢 Recruteur — Parcours Full Automation

#### Étape 1 — Publication d'offre
```
Bot : "Décris le poste à pourvoir. Tu peux parler ou écrire."
🏢 : [Message vocal ou texte]
Bot : [LLM structure l'offre automatiquement]
      "Titre : Commercial terrain
       Ville : Kara
       Salaire : 100 000 - 150 000 FCFA
       Compétences : Vente, négociation, mobilité
       ...

       C'est correct ? (OUI/NON)"
🏢 : "OUI"
Bot : ✅ Offre publiée. Coût : gratuit (offre de lancement).
```

#### Étape 2 — Réception des candidats filtrés
```
Bot : "🏆 8 candidats vérifiés correspondent à votre offre :

       RANG 1 ★★★★★ : Komlan A. (92% match)
       → 4 ans expérience vente terrain, BAC+2
       → Références vérifiées ✓
       → Test vente : 8/10
       → Disponible immédiatement

       RANG 2 ★★★★☆ : Afiwa D. (85% match)
       → 2 ans expérience, BAC G2
       → Références vérifiées ✓
       → Test vente : 7/10
       → Disponible dans 15 jours

       Tapez le RANG pour voir le profil complet."
```

#### Étape 3 — Pré-screening automatique
```
🏢 : "1"
Bot : [Affiche le profil complet + les réponses aux 3 questions préscreening]
      "Komlan A. - 90 12 34 56
       
       Questions posées par IA :
       Q1: 'Avez-vous déjà prospecté en zone rurale ?'
       → Réponse: 'Oui, 2 ans dans le sud Togo'
       
       Q2: 'Acceptez-vous une période d'essai ?'
       → Réponse: 'Oui'
       
       Résumé IA : 'Candidat sérieux, bonne expérience 
       terrain, disponible rapidement. Recommandé.'

       Actions : [1] Contacter  [2] Proposer entretien 
       [3] Engager directement"
```

#### Étape 4 — Embauche + Escrow
```
🏢 : "3"
Bot : "Engager Komlan A. au poste Commercial terrain
       Salaire : 120 000 FCFA/mois
       Commission Talents Togo : 5% (6 000 FCFA) — une seule fois

       Pour garantir l'engagement, déposez le salaire 
       du premier mois (120 000 FCFA) via Flooz/T-money.

       Envoyez 'CONFIRMER' pour recevoir le lien de paiement."
🏢 : "CONFIRMER"
Bot : [Génère un lien CinetPay → Paiement Mobile Money]
      "✅ Paiement reçu. Komlan est notifié.
       Vous avez 15 jours pour confirmer qu'il est actif.
       Après confirmation, les fonds sont libérés."
```

---

## Modules IA Détaillés

### 1. Agent de Parsing CV (Multimodal)

**Input** : Photo de CV, PDF, ou message vocal
**Output** : Profil structuré JSON

```
Entrée: [Image JPEG d'un CV manuscrit scanné]
Sortie: {
  "nom": "ADJOVI",
  "prenom": "Kossi",
  "telephone": "90 12 34 56",
  "ville": "Lomé",
  "diplome": "BAC G2",
  "ecole": "Lycée de Tokoin",
  "annee_diplome": 2022,
  "experiences": [
    {"poste": "Vendeur", "entreprise": "ShopX", "duree": "2 ans"}
  ],
  "competences": ["vente", "gestion stock", "accueil client"],
  "langues": ["français", "ewe"],
  "disponibilite": "immédiate"
}
```

**Prompt LLM** (GPT-4o-mini, ~500 tokens) :
```
Tu es un assistant RH pour le marché togolais.
Extrais les informations du CV ci-dessous au format JSON.
Sois flexible : le CV peut être une photo, un PDF, ou un texte.
Si c'est un message vocal transcrit, extrais les infos de la transcription.
Retourne UNIQUEMENT le JSON, pas d'explication.
```

### 2. Agent de Matching (Embeddings + LLM)

```python
# Étape 1 : Générer les embeddings
job_embedding = openai.embeddings.create(
    model="text-embedding-3-small",
    input=job_description
)
candidate_embeddings = [c.embedding for c in candidates]

# Étape 2 : Similarité cosinus
scores = cosine_similarity(job_embedding, candidate_embeddings)

# Étape 3 : Re-ranking par LLM (top 20 → top 5)
top_20 = candidates[scores.top_k(20)]
prompt = f"""
Poste: {job.titre}
Description: {job.description}

Candidats pré-sélectionnés:
{top_20}

Classe-les du meilleur au pire pour CE poste précis.
Explique une phrase par candidat.
"""
ranking = llm(prompt)
```

### 3. Agent de Quiz Dynamique

**Pas de questions pré-écrites.** L'IA génère les questions à la volée selon :
- Les compétences déclarées
- Le poste visé
- Le niveau d'éducation
- Les questions précédentes (adaptatif)

```
Prompt: 
"Génère 3 questions d'entretien pour un poste de 
COMMERCIAL TERRAIN au Togo. Le candidat a BAC+2 
et 2 ans d'expérience.
Questions en français simple, adaptées au contexte togolais.
Retourne les questions + une grille d'évaluation à 10 points."
```

### 4. Agent de Vérification Automatique

```
Pipeline:
1. Selfie vs Pièce d'identité → Face matching AI (gratuit: face_recognition Python)
2. Vérification téléphone → OTP via SMS/WhatsApp
3. Référence → IA appelle (VAPI.ai) → Tone analysis → Summary
4. Diplôme → Analyse de l'image (fonts, sceaux, métadonnées)
5. Score de confiance final → 0-100%
```

### 5. Agent Anti-Fraude

- Détection des CV dupliqués (embeddings similarity)
- Détection des faux numéros (recyclés, jetables)
- Détection des incohérences chronologiques (LLM)
- Détection des recruteurs frauduleux (historique, pattern)
- Blocage automatique si score de risque > 80%

---

## Intégration Mobile Money (Escrow Automatisé)

### Flow
```
1. Recruteur clique "Engager"
2. Bot génère lien de paiement CinetPay (Flooz + T-money)
3. Recruteur paie 120 000 FCFA
4. Système crédite le wallet interne
5. Notifie le candidat : "Ton salaire est sécurisé ✅"
6. J+15 : Bot demande confirmation aux deux parties
   - "Le candidat travaille-t-il toujours ?" (OUI/NON)
   - Si les deux disent OUI → Libération automatique
   - Si conflit → Escalade admin (prévoir 1 humain)
7. Libération : 114 000 FCFA au candidat (moins 5%)
              + 6 000 FCFA commission (frais inclus)
```

### API CinetPay (exemple)
```bash
# Paiement
curl -X POST https://api.cinetpay.com/v1/payment \
  -H "apikey: ${API_KEY}" \
  -d '{"amount":120000,"currency":"XOF","customer":"90551234"}'

# Vérification statut
curl https://api.cinetpay.com/v1/check?token=${TRANSACTION_TOKEN}

# Payout (versement au candidat)
curl -X POST https://api.cinetpay.com/v1/payout \
  -H "apikey: ${API_KEY}" \
  -d '{"amount":114000,"currency":"XOF","customer":"90123456"}'
```

---

## Canaux et Acquisition

### Phase 1 — Viral WhatsApp (0 FCFA)

1. **Groupes Facebook** — Poster "Cherches du boulot ? Envoie 'EMPLOI' au +228 XX XX XX sur WhatsApp"
2. **Bouche-à-oreille programmé** — Après chaque placement, demande au candidat et au recruteur de partager dans 3 groupes
3. **Scan de CV** — Proposer gratuitement "Je scanne ton CV et te trouve des offres" → le candidat envoie son CV → l'IA parse → il est dans le système
4. **Offre gratuite** — 1 publication gratuite par mois pour les recruteurs → ils testent → ils paient après

### Phase 2 — Télégram pour Régions

**Pourquoi Télégram** : API native gratuite, groupes jusqu'à 200k membres, canaux de diffusion, bots puissants.

Stratégie :
- Canal Télégram "Emploi-Lomé" + "Emploi-Kara" + "Emploi-Sokodé" + "Emploi-Atakpamé" + "Emploi-Dapaong"
- Le bot publie automatiquement les offres triées par région
- Les candidats postulent directement depuis le canal
- Les recruteurs paient pour cibler une région spécifique

### Phase 3 — Boutique Physique Digitale (optionnel)

- Stand dans les marchés : "Dépose ton CV ici → on te trouve du travail"
- Un agent avec une tablette aide les analphabètes à créer leur profil vocal
- 500 FCFA par inscription assistée

---

## Modèle Économique Automatisé

| Flux | Qui paie | Montant | Automatisé ? |
|------|----------|---------|-------------|
| Mise en relation | Recruteur | 5% du salaire 1er mois | ✅ Escrow auto |
| Vérification profil | Candidat | 2 000 FCFA (one-time) | ✅ Quiz + IA |
| Abonnement recruteur | Entreprise | 25 000 FCFA/mois | ✅ Paiement auto |
| Offre premium | Recruteur | 10 000 FCFA/offre (matching IA) | ✅ Paiement auto |
| Escrow fee | Recruteur | 2% des flux | ✅ Intégré |
| Relais régionaux (futur) | Recruteur | 5 000 FCFA/placement région | ✅ Partagé auto |
| Données marché | Écoles / État | 500 000+ FCFA/rapport | ✅ Généré par IA |

### Projection à 12 mois (scénario conservateur)

| Mois | Candidats | Recruteurs | Placements | Revenu mensuel |
|------|-----------|------------|------------|----------------|
| M1 | 200 | 10 | 2 | 12 000 FCFA |
| M3 | 1 000 | 30 | 15 | 250 000 FCFA |
| M6 | 5 000 | 100 | 50 | 1 500 000 FCFA |
| M12 | 20 000 | 400 | 200 | 6 000 000+ FCFA |

---

## Prochaines Étapes Immédiates

### J1-7 : MVP Fonctionnel (capital : 0-50 000 FCFA)
1. **Créer un bot Telegram** avec BotFather (gratuit, 5 min)
2. **Configurer un webhook** → script Python simple (Flask + python-telegram-bot)
3. **Fonctionnalité unique** : collecter profil vocal → Whisper → stocker dans Google Sheets
4. **Tester avec 10 amis** qui cherchent du travail

**Code minimum** :
```python
# bot.py — MVP Telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler
import openai, whisper

async def start(update, context):
    await update.message.reply_text(
        "👋 Bienvenue sur Talents Togo Bot!\n"
        "Envoie un MESSAGE VOCAL pour te présenter.\n"
        "Dis ton nom, ta ville, ton expérience et ce que tu sais faire."
    )

async def handle_voice(update, context):
    # Télécharger le vocal
    voice = await update.message.voice.get_file()
    await voice.download_to_drive("voice.ogg")
    
    # Transcrire
    result = whisper.transcribe("voice.ogg", language="fr")
    texte = result["text"]
    
    # Analyser avec GPT
    profile = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": "Extrais nom, ville, compétences, 
                        expérience de ce message vocal."
        }, {
            "role": "user", "content": texte
        }]
    )
    
    # Stocker (Google Sheets API)
    save_to_sheets(profile.choices[0].message.content)
    
    await update.message.reply_text(
        f"✅ Profil créé !\n{profile.choices[0].message.content}"
    )
```

### J8-30 : Premier Cercle Vertueux
1. **Ajouter WhatsApp** via Meta Cloud API (gratuit)
2. **Ajouter le matching** : collecter des offres réelles manuellement, matcher avec la base
3. **Premier placement** : accompagné (humain) puis automatisé
4. **Itérer** : chaque friction dans le parcours = feature à automatiser

### J30-90 : Automation Complète
1. **Parser CV** (photo/PDF → JSON)
2. **Quiz IA** (génération dynamique de questions)
3. **Escrow** (intégration CinetPay)
4. **Vérification auto** (références par appel vocal IA)
5. **Canaux Telegram régionaux**

---

## Questions Ouvertes (Brainstorming)

- **Comment gérer les litiges d'escrow sans humain ?** → Système de arbitrage automatique basé sur les preuves (captures d'écran, logs WhatsApp)
  
- **Stratégie offline ?** → Kiosques dans les marchés, agents commissionnés pour inscrire les analphabètes

- **Comment éviter les recruteurs frauduleux ?** → Vérification du numéro de contribuable, historique des paiements, notation

- **Faut-il une app mobile ?** → NON. WhatsApp + Telegram suffisent (le téléphone est déjà "l'app")

- **Multilingue ?** → Ewe, Kabyè, Français. L'IA gère tout via Whisper (99 langues supportées)

- **Comment monétiser sans bloquer l'accès ?** → Candidats = gratuit. Recruteurs = freemium. Vérification = payant (optionnel). Escrow = commission.

- **Modèle de données initial ?** → Google Sheets (mois 1), Supabase (mois 2+)

---

## Principe Clé

> *"Africa is not poor. Africa is poorly optimized."* — Principe n°2

Ce système n'invente pas des emplois. Il **optimise** la connexion entre ceux qui cherchent et ceux qui recrutent. À l'échelle, il n'y a pas de limite haute.
