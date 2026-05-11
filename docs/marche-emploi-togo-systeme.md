# Application au Marché du Travail au Togo

## Recherche préliminaire

### État des lieux du marché de l'emploi

| Indicateur | Valeur | Source |
|---|---|---|
| Population active | ~3,8 millions (2020) | Wikipédia |
| Taux de chômage officiel | ~1,9% (2023) | Wikipédia |
| Chômage des jeunes (15-24 ans) | ~22,6% (2023) | Banque Mondiale |
| Âge médian | 19 ans | — |
| Économie informelle | 40-80% du PIB, >85% de l'emploi | — |
| Pénétration smartphone | ~50% et croissante | — |
| PIB par habitant (PPA) | 3 473 $ (2024) | FMI |

### Plateformes existantes

| Plateforme | Type | Taille | Modèle |
|---|---|---|---|
| **Emploi.tg** (Africatalents) | Généraliste | ~1096 offres | Annonces payantes + CVthèque |
| **Job in Togo** (jobintogo.com) | Généraliste | 328 offres / 109 employeurs | Annonces + présélection |
| **ANPE Togo** | Publique | — | Agence gouvernementale |
| **Togocom / Moov Africa** | Initiatives jeunes | — | Programmes de recrutement ciblés |
| **Facebook / WhatsApp** | Informel | Très actif | Groupes, bouche-à-oreille |
| **LinkedIn** | International | Présence limitée | Profils cadres |

### Concurrents / Acteurs régionaux
- **Africatalents** (groupe derrière Emploi.tg) — présent dans 20+ pays africains
- **AfricaWork** — plateforme panafricaine
- **Indeed / LinkedIn** — présence marginale au Togo

---

## Diagnostic systémique (Framework des 4 gaps)

### Gap 1 : Information

**Le problème :**
- Les offres sont éparpillées entre 4+ plateformes
- Pas de standard de format d'offre
- Les CV des candidats n'existent pas en base centralisée
- Un candidat doit visiter 3 sites + 5 groupes Facebook + 2 WhatsApp pour être couvert
- Un recruteur doit publier sur 3 plateformes pour être visible

**Friction concrète :**
> Un jeune diplômé de Kara cherche un emploi. Il doit :
> 1. Aller sur Emploi.tg (connectivité ? data ?)
> 2. Aller sur JobinTogo (autre compte)
> 3. Scroller 15 groupes Facebook
> 4. Envoyer des CV par mail/WhatsApp sans savoir si c'est sérieux
> → 80% abandonnent avant d'avoir postulé

### Gap 2 : Confiance

**Le problème :**
- Impossible de vérifier si une offre est réelle
- Les candidats paient parfois pour "postuler" → arnaques
- Les recruteurs reçoivent 300 CV non filtrés, dont 50% de candidats non qualifiés
- Pas de système de notation des recruteurs ni des candidats
- Les diplômes ne sont pas vérifiables facilement

**Friction concrète :**
> Une PME à Lomé publie une offre. Elle reçoit 200 CV en 3 jours.
> — 80 CV n'ont rien à voir avec le poste
> — 30 sont des faux diplômes
> — Il lui faut 2 semaines pour trier
> → Elle recrute finalement le cousin du voisin (réseau personnel)

### Gap 3 : Distribution

**Le problème :**
- 80%+ des offres sont concentrées sur Lomé
- Les jeunes des régions (Kara, Sokodé, Dapaong, Atakpamé) n'ont pas accès
- Pas de structure pour le recrutement en zones rurales
- Les recruteurs ne savent pas comment atteindre les talents hors Lomé
- La data coûte cher, les sites sont lourds

**Friction concrète :**
> Un technicien qualifié à Sokodé ne voit jamais les offres.
> Les recruteurs ne pensent même pas à chercher hors Lomé.
> → Le marché est réduit à 1/4 du pays.

### Gap 4 : Infrastructure

**Le problème :**
- Pas de registre national des compétences
- Pas de système de vérification des diplômes en ligne
- Pas de matching automatisé compétences ↔ offres
- Pas de données sur le marché du travail (quels métiers recrutent ?)
- Pas de système de préparation aux entretiens / formation pré-emploi

**Friction concrète :**
> Personne ne sait combien de développeurs JavaScript sont disponibles à Lomé.
> Personne ne sait quels métiers seront en demande dans 2 ans.
> → Marché opaque, décisions aveugles.

---

## Le Système à construire

### Vision : Devenir l'infrastructure de confiance du marché du travail togolais

Ne pas être un énième site d'emploi. Devenir **le système** qui connecte, filtre, vérifie et distribue les talents et les offres.

### Architecture en 4 phases (capital progressif)

---

## Phase 1 — L'Annuaire des Compétences (Capital : 0 FCFA)

**Problème résolu** : Information centralisée.

### Comment faire
1. Crée une base de profils sur Google Sheets / Airtable
2. Parcours les groupes Facebook "Emploi Togo", "Recrutement Lomé"
3. Collecte les profils des candidats (nom, compétences, téléphone, localisation)
4. Crée un groupe WhatsApp "Talents Togo"
5. Quand un recruteur cherche quelqu'un, tu sors de ta base les 5 meilleurs profils

### Sources de talent gratuites
- Groupes Facebook "Recrutement Togo", "Emploi Lomé"
- Défilés de fin d'année des écoles (ESA, ESGIS, EAMAU, UL)
- Apprentis et artisans du secteur informel

### Monétisation
- Commission de mise en relation : 5 000-10 000 FCFA par placement
- Forfait annuaire pour recruteurs : 25 000 FCFA/mois pour accès base

### Exemple quotidien
> Un hôtel cherche un réceptionniste anglais-français.
> Tu fouilles ta base, tu trouves 3 profils.
> Tu les présentes, l'hôtel choisit, tu touches 10 000 FCFA.

---

## Phase 2 — La Vérification (Capital : 50 000-100 000 FCFA)

**Problème résolu** : Confiance (trust deficit).

### Comment faire
1. Tu deviens le vérificateur : tu confirmes que les candidats existent
2. Appels téléphoniques de référence : tu parles aux anciens employeurs
3. Vérification des diplômes : tu confirmes avec les écoles
4. Test de compétences de base : tu fais passer un mini-test (français, Excel, etc.)
5. Tu délivres un "badge vérifié" consultable par les recruteurs

### Pourquoi ça marche
- Les recruteurs reçoivent 200 CV non triés → les CV vérifiés passent en premier
- Les bons candidats paient pour être vérifiés (ils se démarquent)
- Les recruteurs paient pour n'avoir que des profils vérifiés

### Monétisation
- Candidats : 2 000-5 000 FCFA pour vérification + badge
- Recruteurs : 50 000 FCFA/mois pour accès aux profils vérifiés

---

## Phase 3 — La Distribution Régionale (Capital : 100 000-200 000 FCFA)

**Problème résolu** : Distribution (offres hors Lomé).

### Comment faire
1. Recrute des "relais emploi" dans chaque grande ville (Kara, Sokodé, Atakpamé, Dapaong)
2. Ce sont des gens qui diffusent les offres localement (sur WhatsApp, affichage, bouche-à-oreille)
3. Collecte les CV des candidats locaux dans ta base
4. Propose aux recruteurs basés à Lomé de trouver des talents en région (moins chers, plus fidèles)

### Modèle
- Les relais sont payés à la commission (5 000 FCFA par candidat placé)
- Pas de salaire fixe → coût zéro si pas de placement

### Opportunité unique
> Un recruteur à Lomé cherche 10 opérateurs de saisie.
> À Lomé, personne n'accepte à 80 000 FCFA/mois.
> À Kara ou Sokodé, 80 000 FCFA est un bon salaire.
> Tu connectes les deux — tu prends 10 000 FCFA par placement × 10 = 100 000 FCFA.

---

## Phase 4 — Le Matching Intelligent + Escrow (Capital : 500 000+ FCFA)

**Problème résolu** : Infrastructure (matching + paiement sécurisé).

### Comment faire
1. Construis une plateforme mobile-first (PWA simple, pas une app lourde)
2. Les recruteurs publient des offres avec critères précis
3. Le système matche automatiquement avec les profils vérifiés
4. Escrow des salaires : le recruteur dépose le salaire du 1er mois sur ton système
5. Tu libères au candidat après 15 jours de travail effectif

### Pourquoi l'escrow change tout
- Le recruteur est sûr que le candidat va venir (l'argent est déjà déposé)
- Le candidat est sûr d'être payé (l'argent est sécurisé)
- Tu réduis le risque des deux côtés → le marché s'ouvre

### Monétisation
- Commission recruteur : 5-10% du salaire la première année
- Commission candidat : 0% (tu attires les candidats)
- Escrow : frais de 2% sur les flux

---

## Synthèse : Pourquoi ce système gagne

### Analyse des 8 principes

| Principe | Application |
|----------|-------------|
| **1. Problème systémique** | L'emploi n'est pas un problème de "pas d'offres" mais d'information, confiance, distribution |
| **2. Pas pauvre, mal optimisé** | Des milliers de candidats compétents existent mais ne sont pas connectés aux recruteurs |
| **3. 4 gaps** | Information (éparpillement), Confiance (arnaques), Distribution (Lomé-centrisme), Infrastructure (pas de matching) |
| **4. Friction = marché** | Chaque friction résolue (vérification, matching, escrow) est une ligne de revenus |
| **5. Demande existe** | Les recruteurs cherchent, les candidats cherchent — le problème est la connexion |
| **6. Système > Business** | Devient l'infrastructure de référence du marché du travail togolais |
| **7. Confiance système** | L'escrow + vérification remplacent l'absence d'institutions fiables |
| **8. Rentabilité structurelle** | Chaque placement = commission. Plus le réseau grandit, plus il est efficace |

### Avantage concurrentiel

- **Effet de réseau** : Plus de candidats vérifiés → plus de recruteurs → plus de candidats (cycle vertueux)
- **Barrière à l'entrée** : Les concurrents (Emploi.tg, JobinTogo) n'ont pas la vérification ni l'escrow
- **Données** : Tu sais quels métiers recrutent, quels salaires, où → valeur pour les écoles, gouvernement, entreprises
- **Coût de switching** : Les recruteurs qui utilisent ton système ne peuvent pas revenir aux CV non vérifiés

---

## Plan d'action immédiat (0 FCFA, démarrage demain)

### Semaine 1-2 : Constitution de la base
- Rejoins 10 groupes Facebook "Emploi Togo"
- Copie les profils des candidats dans un Google Sheet
- Note : nom, tel, compétences, localisation, expérience
- Objectif : 100 profils en 2 semaines

### Semaine 3-4 : Premières mises en relation
- Contacte 10 recruteurs (PME, ONG, hôtels, commerces)
- Propose-leur : "Je te trouve des candidats gratuits, tu paies seulement si ça marche"
- À chaque placement, propose la vérification comme service payant
- Objectif : 5 placements, 50 000-100 000 FCFA de commission

### Mois 2 : Boucle vertueuse
- Avec l'argent des commissions, commence la vérification (appels, tests)
- Déploie les premiers relais à Kara et Sokodé
- Objectif : 500 profils dans la base, 10 placements/mois

### Mois 3 : Infrastructure logicielle
- Avec 200 000-300 000 FCFA de trésorerie, fais développer une PWA simple
- Intègre les 3 services : annuaire + vérification + matching
- Prépare l'escrow (partenariat avec Flooz/T-money)

---

## Citation

> *"The problem is not demand. There will always be a demand for a product. But the problem is distribution and trust."*
> — Principe n°5

> *"I'm not just opening a business, I'm building a system that removes that friction."*
> — Principe n°6
