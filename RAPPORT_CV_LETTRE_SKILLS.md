# Rapport : Amélioration de la Génération de CV et Lettres de Motivation

## 1. Analyse du Système Actuel

### 1.1 Architecture de Génération

Le projet **leRH** dispose déjà d'un système complet de génération de documents via la classe `DocumentGenerator` (`src/leRH/core/documents/generator.py`).

#### Flux de génération :

1. **Entrée** : Profil utilisateur (User) + Offre d'emploi (Job) + Analyse CV optionnelle
2. **Appel LLM** : Le modèle génère du contenu structuré en JSON
3. **Parsing** : Extraction et validation JSON
4. **Rendu** : Génération DOCX/PDF avec mise en page ATS-friendly

### 1.2 Prompts Actuels

#### Prompt CV (`CV_GENERATION_PROMPT`)

```python
CV_GENERATION_PROMPT = """You are an expert resume writer specializing in ATS (Applicant Tracking System) optimization. Generate a tailored, ATS-friendly CV in French..."""
```

**Règles ATS appliquées :**
- Sections standardisées : "Résumé Professionnel", "Compétences Clés", "Expérience Professionnelle", "Formation"
- Pas de graphics, images, tables, colonnes
- Mots-clés de l'offre intégrés naturellement
- Quantification des réalisations
- Ordre chronologique inversé (max 10-15 ans)

**Structure de sortie JSON :**
```json
{
  "summary": "Résumé professionnel 3-5 phrases",
  "core_competencies": ["skill1", "skill2"],
  "experience": [{"company", "location", "title", "start_date", "end_date", "bullets"}],
  "education": [{"degree", "institution", "year"}],
  "certifications": ["cert1"],
  "languages": ["Langue (Niveau)"]
}
```

#### Prompt Lettre de Motivation (`COVER_LETTER_PROMPT`)

```python
COVER_LETTER_PROMPT = """You are an expert in writing professional cover letters in French..."""
```

**Structure :**
- 4 paragraphes maximum
- Ton professionnel et chaleureux
- Inclure titre du poste et nom de l'entreprise

**Structure de sortie JSON :**
```json
{
  "recipient": "À l'attention du recruteur",
  "subject": "Candidature au poste de [Job Title]",
  "body_paragraphs": ["para1", "para2", "para3", "para4"],
  "closing": "Sincères salutations"
}
```

### 1.3 Outils de l'Assistant Koffi

L'agent Koffi (`manager.py:129-354`) dispose de deux outils function calling :

| Outil | Description | Coût |
|-------|-------------|------|
| `generate_cv` | Génère un CV ATS optimisé pour une offre | 5 crédits |
| `generate_cover_letter` | Génère une lettre de motivation personnalisée | 3 crédits |

**Workflow actuel :**
1. L'utilisateur demande un document ou Koffi le propose
2. Koffi affiche un résumé du profil et demande confirmation
3. Après confirmation, lancement en arrière-plan
4. Déduction des crédits et notification à l'utilisateur

### 1.4 Limites Identifiées

1. **Prompt générique** : Les prompts actuels sont corrects mais pourraient être enrichis avec des techniques de prompting avancées (few-shot, chain-of-thought)
2. **Pas de suivi de versions** : Pas de versionnage des documents générés
3. **Personnalisation faible** : Pas d'adaptation au niveau d'expérience (junior/senior), au secteur, ou au type de contrat
4. **Pas d'itération** : L'utilisateur ne peut pas demander de modifications après génération

---

## 2. Proposition de Skills de Rédaction

### 2.1 Principes de Design

Les skills proposés visent à :
- **Augmenter la qualité** des documents générés via des techniques de prompting avancées
- **Personnaliser** selon le contexte (secteur, niveau, type de poste)
- **Donner plus de contrôle** à l'utilisateur sur le résultat

### 2.2 Skill 1 : `cv-optimization`

**Objectif** : Appliquer des techniques d'optimisation avancées selon le contexte.

**Fonctionnalités :**
- Analyse du niveau d'expérience (junior/mid/senior)
- Adaptation du format selon le secteur (tech, finance, santé, enseignement)
- Optimisation pour les ATS spécifiques (LinkedIn, Indeed, APEC)
- Suggestions d'amélioration si le profil est faible

**Prompt spécialisé :**

```python
CV_OPTIMIZATION_PROMPT = """Tu es un expert en rédaction de CV ATS avec {years_years} d'expérience dans le secteur {sector}.
Tu dois créer un CV adapté à {target_platform} pour le poste de {job_title}.

CONTEXTE SPECIFIQUE:
- Niveau d'expérience: {experience_level}
- Secteur: {sector}
- Plateforme cible: {target_platform}
- Mots-clés ATS prioritaires: {ats_keywords}

TECHNIQUES A UTILISER:
1. Pour niveau junior: Mettre en avant formation, stages, projets, soft skills
2. Pour niveau senior: Valoriser leadership, réalisations mesurables, stratégique
3. Pour tech: Quantifier le code delivered, projets open source, certifications cloud
4. Pour finance: Mentionner certifications (CFA, AMF), conformité, gère de budgets
5. Pour santé: Souligner diplômes, éthique, expériences患者

Format de sortie:
{json_schema}"""
```

### 2.3 Skill 2 : `cover-letter-crafting`

**Objectif** : Créer des lettres de motivation véritablement personnalisées et percutantes.

**Fonctionnalités :**
- Analyse de l'offre pour identifier les critères clés
- Recherche d'informations sur l'entreprise (si disponibles)
- Personnalisation du ton (formalité, créativité)
- Structure adaptative selon le contexte

**Modèle de lettre optimisé (basé sur les recherches) :**

| Élément | Description | Exemple |
|---------|-------------|---------|
| Accroche | Question, anecdote, ou fait marquant sur l'entreprise | "Votre croissance de 40% en 2024..." |
| Connexion | Lien entre compétences et besoins spécifiques | "Mon expérience en SEO..." |
| Preuve | Exemple concret chiffré | "J'ai augmenté le trafic de 150%" |
| Action | Call-to-action | "Je serais ravi d'en discuter" |

**Prompt spécialisé :**

```python
COVER_LETTER_CRAFT_PROMPT = """Tu rédiges une lettre de motivation {tone} pour {sector}.

OFFRE D'EMPLOI:
{job_description}

PROFIL CANDIDAT:
{profile}

INFORMATIONS ENTREPRISE (optionnel):
{company_info}

STRUCTURE OBLIGATOIRE:
1. **Accroche** (2-3 lignes): Commence par une question, un fait sur l'entreprise, ou une anecdote pertinente - JAMAIS par "Je postule"
2. **Corrélation** (3-4 lignes): Explique POURQUOI ce poste t'attire spécifiquement, pas juste "je cherche un emploi"
3. **Preuve** (3-4 lignes): Un exemple CONCRET et CHIFFRÉ d'une réalisation pertinente
4. **Clôture** (2 lignes): Proposition d'entretien, remercie

REGLES:
- MAX 250 mots, 4 paragraphes courts
- Pas de répétitions du CV
- Intégrer 2-3 mots-clés de l'offre naturellement
- Éviter les clichés: "travailleuse", "dynamique", "motivée" sans preuve
- Ton {tone} (professionnel décontracté / corporate / créatif)

EXEMPLE D'ACCROCHE A NE PAS FAIRE:
❌ "Je постule avec grand intérêt au poste de..."

EXEMPLE D'ACCROCHE A FAIRE:
✅ "Votre projet de expansion en Afrique de l'Ouest m'inspire particulièrement...""""
```

### 2.4 Skill 3 : `cv-review-and-refine`

**Objectif** : Permettre la révision interactive des documents.

**Fonctionnalités :**
- Analyse du CV généré et identification des faiblesses
- Propositions de modifications ciblées
- Réécriture de sections spécifiques
- Ajustement du ton ou du format

**Outil supplémentaire :**

```python
TOOL: improve_cv_section
PARAMETERS:
  - section: "experience" | "skills" | "summary"
  - feedback: "string - what to improve"
  - target_job: "string"

OUTPUT: Version améliorée de la section
```

---

## 3. Meilleur Modèle de Lettre de Motivation

### 3.1 Modèle Recommandé (Basé sur les Bonnes Pratiques 2024-2025)

**Structure optimale :**

```
[Prénom Nom]
[Téléphone] | [Ville]

[Date]

[Entreprise]
À l'attention de [Nom ou service]

Objet : Candidature au poste de [Titre] - [Référence]

[Madame, Monsieur, Nom si connu],

[PARAGRAPHE 1 - ACCROCHE - 3 lignes max]
Question ou fait marquant sur l'entreprise/poste qui montre votre intérêt sincère.
Exemple: "Votre positionnement unique sur le marché togolais..." ou "Cette fonction correspond exactement à mon parcours..."

[PARAGRAPHE 2 - CORRESPONDANCE - 4-5 lignes]
Pourquoi CE poste et CETTE entreprise ? Évitez le générique.
Connexion entre VOTRE parcours et LEURS besoins spécifiques.

[PARAGRAPHE 3 - PREUVE - 4-5 lignes]
Un exemple CONCRET et CHIFFRÉ d'une réalisation pertinente.
Pas "j'ai géré un budget" mais "j'ai réduit les coûts de 25% en optimisant les processus"

[PARAGRAPHE 4 - CONCLUSION - 2-3 lignes]
Proposition d'entretien + remerciement + disponibilité.

Je reste à votre disposition pour un échange rapide.
Merci pour votre considération.

[Sincères salutations / Bien cordialement]
[Prénom Nom]
[Téléphone]
```

### 3.2 Différenciateurs Clés

| Élément | À faire | À éviter |
|---------|---------|----------|
| **Accroche** | Question, fait entreprise, anecdote | "Je postule avec grand intérêt" |
| **Tonalité** | Authentique, conversational | Formules toutes faites |
| **Preuves** | Chiffres, résultats concrets | "je suis rigoureux" sans exemple |
| **Longueur** | 200-250 mots max | Roman, paragraphe trop long |
| **Mots-clés** | 2-3 de l'offre, naturelle | Trop, mal intégré |

### 3.3 Adaptation par Profil

| Profil | Accent | Exemple de preuve |
|--------|--------|-------------------|
| **Junior** | Formation + potentiel | Projet académique, stage |
| **Senior** | Leadership + stratégie | Management, transformations |
| **Reconversion** | Compétences transférables | Ce qui lie l'ancien au nouveau |
| **Spontanée** | Connaissance entreprise | Pourquoi cette entreprise |

---

## 4. Implémentation Recommandée

### 4.1 Architecture

```
src/leRH/core/documents/
├── generator.py          # Existant
├── prompts/
│   ├── __init__.py
│   ├── cv_templates.py   # Prompts par niveau/secteur
│   └── cover_letter_templates.py
└── skills/
    ├── __init__.py
    ├── cv_optimizer.py   # Skill CV
    └── cover_letter_crafter.py
```

### 4.2 Nouveau Prompt avec Few-Shot

```python
COVER_LETTER_WITH_EXAMPLES = """Tu rédiges une lettre de motivation française professionnelle.

EXEMPLES DE BONNES ACCROCHES:
- Pour une	startup: "L'esprit d'innovation de [Entreprise] résonne avec ma vision..."
- Pour une ONG: "Votre mission d'impact social m'inspire particulièrement..."
- Pour une banque: "Votre réputation de fiabilité m'a immédiatement attiré..."

TAACHE: Rédige une lettre basée sur:
Poste: {job_title}
Entreprise: {company}
Candidat: {profile}

Sortie JSON:
{
  "hook": "Accroche originale basée sur l'entreprise",
  "body": ["para1", "para2", "para3"],
  "closing": "Proposition d'entretien concise"
}
"""
```

### 4.3 Intégration avec Koffi

Ajouter un nouveau skill dans le manager:

```python
# Nouveau tool dans _build_tools()
{
    "type": "function",
    "function": {
        "name": "improve_document",
        "description": "Améliore une section spécifique du CV ou de la lettre générée",
        "parameters": {
            "type": "object",
            "properties": {
                "document_type": {"type": "string", "enum": ["cv", "cover_letter"]},
                "section": {"type": "string"},
                "feedback": {"type": "string"}
            }
        }
    }
}
```

---

## 5. Recommandations Finales

### Priorités d'implémentation

1. **Court terme** : Enrichir les prompts existants avec les techniques ci-dessus (few-shot, exemples)
2. **Moyen terme** : Créer le skill `cover-letter-crafting` avec le modèle recommandé
3. **Long terme** : Ajouter le système de révision interactive

### Métriques de Succès

- Taux de téléchargement des documents générés
- Feedback utilisateur sur la qualité
- Taux de réponse aux candidatures (si traçable)

### Sources

- Hellowork (2024): https://www.hellowork.com/fr-fr/medias/lettre-motivation-2024-astuces.html
- Resumity (2024): https://www.resumity.fr/faire-un-lettre-de-motivation/
- TopCV (2025): https://topcv.fr/conseils-emploi/guide-de-redaction-dune-lettre-de-motivation
- L'Étudiant: https://www.letudiant.fr/jobsstages/lettres-de-motivation_1/