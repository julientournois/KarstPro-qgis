# KarstPro — Document technique : critères, seuils, outils, modèles

**Version : 1.13.0**

> Annexe optionnelle au guide d'utilisation (`KarstPro_Documentation.pdf`,
> fourni à côté de ce fichier) : le détail complet de
> **comment** et **pourquoi** KarstPro détecte et priorise ainsi — quels
> critères, quels seuils, quels logiciels, quels modèles statistiques, avec
> leurs chiffres de validation. Rien n'est nécessaire à lire ici pour utiliser
> le plugin ; ce document sert à qui veut comprendre le calcul en profondeur
> ou vérifier sa rigueur scientifique.
>
> Toutes les valeurs de ce document sont extraites du code source à la version
> ci-dessus : `karstpro/config/default_scoring.json`,
> `karstpro/models/barrois_model.json`, `karstpro/core/*.py`,
> `validation/inventaire/`. Aucune n'est approximée.

---

## 0. Vue d'ensemble — deux choses à ne pas confondre

KarstPro fait deux opérations de nature très différente :

1. **Détection** (déterministe, géométrique) : extraire du MNT LiDAR les
   **dolines** (cuvettes fermées) et les **gouffres** (puits verticaux). C'est
   de la morphométrie pure, sans apprentissage.
2. **Priorisation** (scoring) : classer les dolines détectées par intérêt
   spéléologique. Deux régimes :
   - **mode exploratoire** : barème morphologique à poids *a priori* (hors
     domaine validé) ;
   - **modèle appris** : régression logistique calibrée et validée
     hors-échantillon (domaines validés, ex. le Barrois).

La détection ne « sait » pas s'il y a une cavité ; elle trouve des formes. Le
scoring estime une probabilité d'intérêt. Le document traite les deux.

---

## 1. Chaîne de traitement — outils, librairies, algorithmes par phase

| Phase | Rôle | Outils / librairies | Algorithme / méthode |
|---|---|---|---|
| **1. Acquisition LiDAR** | Télécharger les dalles utiles | API IGN Géoplateforme, `requests` | Format **COPC LAZ**, lecture partielle par **HTTP Range** (téléchargement de la seule emprise) |
| **2. Génération MNT 1 m** | Nuage de points → raster sol | **PDAL** (CLI fourni avec QGIS), **GDAL** | Filtre **classe LAS 2 (sol)** → interpolation raster 1 m (`writers.gdal`) |
| **3a. Détection dolines** | Cuvettes fermées | **WhiteboxTools**, `rasterio`, `numpy` | **Remplissage des dépressions (Wang & Liu 2006)** ; profondeur = MNT comblé − MNT brut ; vectorisation `rasterio.features.shapes` |
| **3b. Détection gouffres** | Puits verticaux | `numpy`, `rasterio` (purs) | Signature de **vide NODATA compact à bord de sol valide** : masque NODATA → érosion morphologique → étiquetage BFS → filtres taille/compacité/couronne |
| **3c. Points d'eau** | Sources / pertes référencées | WFS **BD Topo** (Géoplateforme), `geopandas` | *Référencement* (pas de détection) : `noeud_hydrographique`, `detail_hydrographique` |
| **4. Attributs morphométriques** | Décrire chaque doline | `numpy`, **WhiteboxTools** | Pente p90 sur l'anneau de bord, **TPI 500 m** (moyenne focale par image intégrale), **bassin versant D8** (`d8_flow_accumulation`) |
| **5. Contexte géologique** | Lithologie + contact | WFS **BRGM** (BD Charm-50 1/50 000, repli LITHO_1M), `geopandas`, `shapely` | Jointure spatiale, distance au contact karstifiable, facteur de karstifiabilité par **NOTATION** |
| **6. Scoring / priorisation** | Classer P1/P2/P3 | `numpy` (pur) | Barème pondéré **ou** régression logistique (inférence numpy, **sans scikit-learn** au runtime) |
| **7. Exports** | Livrables terrain/analyse | `geopandas` (GeoPackage), QField, `reportlab` (PDF) | Projet QField, GPX, prompt MLL, rapport PDF |

**Notes d'implémentation importantes :**
- **Aucune dépendance scikit-learn** n'est requise pour faire tourner le plugin :
  le modèle appris est sérialisé en JSON (coefficients + scaler) et l'inférence
  est du pur `numpy`.
- **`pyproj` est volontairement évité** dans les threads de traitement (non
  thread-safe sur QGIS 4.0.2 → access violation) : conversions L93↔WGS84 en pur
  Python, lectures GeoPackage en SQL direct.

---

## 2. Seuils et critères de détection (et leur justification)

### 2.1 Dolines — cuvettes fermées

| Critère | Valeur | Pourquoi |
|---|---|---|
| Résolution MNT | **1 m** | Résolution LiDAR HD IGN ; plus fin = bruit, plus grossier = on rate les petites dolines |
| Classe de points | **LAS 2 (sol)** seule | Élimine végétation/bâti ; on veut le sol nu |
| Remplissage | **Wang & Liu 2006** (WhiteboxTools `fill_depressions`) | Standard hydrologiquement cohérent pour identifier les dépressions fermées |
| Profondeur minimale | **> 0,1 m** | En-deçà = bruit d'interpolation du MNT 1 m, pas une vraie dépression |
| Surface minimale | **≥ 10 m²** | En-deçà = artefact ponctuel ; une doline exploitable fait au moins quelques m² |

La détection est **purement automatique** à cette étape : aucun réglage manuel,
résultat reproductible entre opérateurs.

### 2.2 Gouffres — puits verticaux (`core/shafts.py`)

Un puits vertical ouvert ne renvoie **aucun écho sol** au LiDAR (les impulsions
plongent dans le vide) : il apparaît comme un **trou de NODATA compact** bordé
de sol valide — et **non** comme une cuvette. La détection de dolines y est donc
structurellement aveugle ; ce module le rattrape par sa signature inverse.

| Paramètre | Valeur | Rôle / pourquoi |
|---|---|---|
| `min_area_m2` | **6 m²** | Plancher : sous 6 m², trop petit / bruité |
| `max_area_m2` | **400 m²** | Plafond : au-delà = plan d'eau ou grande lacune de canopée, pas un puits |
| `min_fill` (compacité) | **0,45** | Aire / aire de la bbox : un puits est rond/compact, une trouée de canopée est filandreuse |
| `min_valid_ring` | **0,6** | Fraction de **sol valide** dans la couronne autour du vide : un puits a un bord net ; une trouée de canopée baigne dans le NODATA |
| `ring_px` | **4** | Épaisseur (cellules) de la couronne testée |
| Érosion morphologique | 1 passe | Casse les **fils fins (≤ 2 px)** de canopée reliant les vides ; les cœurs compacts (un puits) survivent |

**Filtre anti-faux-positifs BD Topo** : un vide de NODATA sur un **bâtiment** (le
LiDAR voit le toit) ou un **plan d'eau** (pas de retour) n'est pas un gouffre. On
l'écarte par proximité (**buffer 5 m**) aux polygones BD Topo `batiment` /
`plan_d_eau` / `surface_hydrographique`. La requête WFS est **paginée**
(`STARTINDEX`) car la Géoplateforme plafonne à 5000 entités/réponse — sans ça, en
zone urbaine dense des milliers de bâtiments manquaient et les gouffres posés
dessus échappaient au filtre.

**Limites assumées (le vide n'est pas toujours dans le MNT) :**
- **canopée dense** : faux positifs résiduels non filtrables par BD Topo ;
- **gouffres noyés** (inversac) : le LiDAR se réfléchit sur l'eau → pas de vide → invisibles ;
- **gouffres aménagés** (Padirac, coiffés de bâti) : le LiDAR voit la structure.

→ Tous les candidats gouffres sont marqués **« à vérifier sur le terrain »**.

### 2.3 Points d'eau — `bdtopo_eau` (référencement, pas détection)

Sources, pertes, inversacs, résurgences, exutoires **déjà cartographiés** en BD
Topo. Ce n'est **pas** de la détection : on localise des features connues
(comme l'inventaire Géorisques), pour combler l'angle mort des entrées noyées.

### 2.4 Signal ponctuel de puits — colonnes `pc_*` (informatif, hors scoring)

Troisième signal, **complémentaire** aux dolines (§2.1) et aux gouffres (§2.2),
introduit en v1.10.0. Il exploite le **nuage de points brut**, pas le MNT.

**Le problème.** Un puits étroit peut ne laisser passer qu'une poignée de
retours LiDAR jusqu'au fond. Ces quelques points survivent dans le nuage brut,
mais disparaissent au moment où le MNT est lissé/interpolé : la doline en
surface paraît alors banale (quelques m², peu profonde). Ni la détection de
cuvettes (§2.1) ni celle de vides NODATA (§2.2) ne voient ce cas.

**Méthode.** On rasterise les **derniers retours uniquement**
(`ReturnNumber == NumberOfReturns`) en deux bandes (min, count) via PDAL, puis
on compare cette altitude minimale au MNT. Une cellule est retenue si elle
plonge à la fois **> 1 m sous le MNT** et **> 1 m sous la médiane de son
voisinage** (fenêtre 9×9, numpy pur). Colonnes produites : `pc_plongee_m`,
`pc_dist_m`, `pc_n_points`. Un seuil de surface (`SEUIL_SURFACE_PC`) permet de
restreindre le test aux petites dolines ; **par défaut, toutes les dolines
sont testées**. Depuis le 2026-07-29, ce n'est plus un champ de la fenêtre de
préparation (rarement changé) — modifiable en éditant `karstpro_etude.json`
puis « Refaire une étude ».

> ⚠️ **Seuil de surface — hypothèse initiale réfutée.** Le défaut valait 50 m²
> à la livraison (v1.10.0), sur l'idée que « le signal n'a de sens que sur les
> petites dolines » — une intuition jamais vérifiée. Mesuré le 2026-07-26 sur
> **5 secteurs**, contre les inventaires de cavités connues (rayon 20 m), le
> signal est **au moins aussi prédictif sur les dolines ≥ 50 m²** :
>
> | Secteur | ratio < 50 m² | ratio ≥ 50 m² |
> |---|---|---|
> | Marnaval | 2,6× | **7,2×** |
> | Beurey | 4,9× | 4,6× |
> | Besain | 3,9× | 4,0× |
> | Molain | 4,1× | **12,8×** |
> | Arc-sous-Cicon | 5,2× | **7,1×** |
>
> Le taux de détection reste par ailleurs stable (8,6–9,0 %) quel que soit le
> seuil : pas d'explosion de faux positifs sur les grandes surfaces. L'ancien
> défaut excluait donc précisément la population où le signal fonctionne le
> mieux — et qui contient **78 % des dolines rouges** (57/73 sur Marnaval).
> Seuil par défaut relevé pour couvrir toutes les dolines.

> ⚠️ **Alignement des grilles — piège vérifié.** Le raster des derniers retours
> et le MNT sont produits par deux appels PDAL distincts ; sans contrainte,
> chacun cale sa propre grille sur l'emprise de ses points (décalage
> sub-métrique). Un rééchantillonnage naïf comparait alors des cellules sans
> rapport et produisait des « plongées » de 30–50 m au lieu de 2–5 m réels.
> `generate_pc_rasters` force donc `origin_x`/`origin_y`/`width`/`height` de
> `writers.gdal` sur la grille exacte du MNT — lecture directe, aucun
> rééchantillonnage.

**Validation croisée (2026-07-25).** Contre les inventaires de cavités connues,
sur **8 secteurs / 2 régions géologiques**, une doline portant le signal a
**2,2× à 6×** plus de chances d'avoir une cavité connue à ≤ 20 m qu'une doline
sans (détail par secteur dans `docs/JOURNAL_EXPERIENCES.md`, outil
`prototypes/validate_pc_signal.py`). Le signal est aussi **corrélé au score
existant** (16,4 % des rouges le portent, contre 3–4,5 % des jaunes/grises sur
Marnaval) : il n'est donc pas un axe indépendant du modèle.

**Statut : informatif uniquement.** Le signal **n'entre pas** dans le score ni
dans la priorité, et aucun modèle n'a été réentraîné avec. C'est un choix
délibéré (Phase 1) : la corrélation ci-dessus est encourageante mais reposerait
sur un plafond d'échantillon trop faible pour justifier de toucher à un scoring
déjà validé. L'utilisateur voit un anneau sur la doline concernée et une
section dédiée du rapport MLL ; il tranche lui-même.

### 2.4.1 Limites mesurées — à connaître avant d'exploiter le signal

**a) Sous-détection sous canopée fermée (faux négatifs systématiques).** La
méthode exige que des derniers retours atteignent le fond du puits. Sous forêt
dense, la majorité des impulsions est interceptée par la végétation : il reste
trop peu de points au sol pour que le critère se déclenche. Mesuré sur Marnaval
(2208 dolines sous végétation fermée BD Topo contre 991 à découvert) :

| Zone | Dolines | Avec signal | Taux | Médiane `pc_n_points` |
|---|---|---|---|---|
| sous canopée fermée | 2208 | 163 | **7,4 %** | 74 |
| hors canopée | 991 | 113 | **11,4 %** | 134 |

C'est la **même physique** que les faux positifs de gouffres sous canopée
(§2.2), mais inversée : là un vide de végétation imite un puits, ici la
végétation masque un vrai puits. Conséquence directe : **l'absence de signal
n'infirme rien**, et encore moins en secteur boisé. Un secteur forestier
produira mécaniquement moins d'anneaux sans contenir moins de puits.

**b) Biais de découvrabilité — testé, largement écarté.** Les dolines à signal
sont plus proches du bâti (médiane 128 m contre 318 m), ce qui pourrait faire
craindre que la corrélation avec les cavités connues mesure surtout
l'accessibilité (zones déjà prospectées) plutôt que le karst. Contrôle négatif
sur Marnaval, en ne gardant que les 1131 dolines à **plus de 500 m de tout
bâti** : le signal conserve un ratio de **4,9×** (16,2 % contre 3,3 %). Le
biais existe donc, mais n'explique pas l'effet. La proximité au bâti s'explique
d'ailleurs par le point (a) : moins de forêt près des villages.

**c) La validation reste un proxy.** Tous les chiffres ci-dessus mesurent la
corrélation avec des **cavités déjà connues** — pas avec « il y a quelque chose
à trouver ». Or une cavité connue n'est pas un objectif de prospection, et
« aucune cavité connue à proximité » ne veut pas dire « aucune cavité » (souvent
personne n'a cherché). Seule une **validation terrain en aveugle, sur paires
appariées** (même priorité, même surface, même profondeur — la seule différence
étant le signal) trancherait ; cf. `validation/terrain/PROTOCOLE.md`. Ordre de
grandeur du coût : ~158 visites pour détecter un effet aussi fort que celui
observé (16 % contre 3 %), ~658 pour un effet faible (20 % contre 12 %). C'est
la contrainte dure, pas la méthode.

### 2.5 Signal d'affaissement historique — colonne `rge_contrast_m` (contribue au score, domaine-dépendant)

Quatrième signal, introduit en v1.11.0 (`core/rgealti.py`). Contrairement au
signal ponctuel (§2.4), **celui-ci entre dans le modèle appris** là où il a été
validé — c'est une différence de statut volontaire, décidée après discussion
explicite avec l'utilisateur (le seuil de preuve exigé pour le signal ponctuel
n'a jamais été jugé prohibitif ; ici la preuve mesurée a été jugée suffisante
pour justifier l'intégration).

**Le principe.** L'IGN republie régulièrement des relevés LiDAR d'une même
zone (RGE ALTI, souvent 2009-2016 selon la campagne, contre LiDAR HD récent).
Un soutirage karstique actif entre les deux dates laisse une trace : le sol
s'est affaissé, donc `z_lidar_hd < z_rgealti` localement. La méthode :

1. **Téléchargement aligné** : RGE ALTI récupéré en tuiles WMS (`image/x-bil`,
   float32, EPSG:2154) sur exactement la même grille que le MNT LiDAR HD déjà
   généré pour le secteur (`fetch_rgealti_for_secteur`).
2. **Retrait du biais systématique** : `diff = z_lidar_hd - z_rgealti`, puis un
   **fond régional** est estimé par médiane sur blocs de 50 m, ré-échantillonné
   en bilinéaire (numpy pur, pas de scipy — convention du projet) ; `residual =
   diff - fond`. Ce retrait est nécessaire car les deux relevés ont des biais
   verticaux systématiques indépendants du karst (géoïde, calibration).
3. **Contraste doline** : moyenne du `residual` dans un anneau extérieur
   (60 m) moins la moyenne dans le disque intérieur (15 m) → `rge_contrast_m`.
   Négatif = affaissement relatif au centre de la doline (signal recherché).

**Contrôle de qualité obligatoire (`is_secteur_eligible`).** Le RGE ALTI est un
produit hétérogène au niveau national : LiDAR par endroits, **corrélation
photogrammétrique** ailleurs (bien moins précise, lissée). `estimate_roughness`
mesure l'écart-type d'un filtre laplacien 3×3 (numpy pur) sur le RGE ALTI ; en
dessous de `ROUGHNESS_THRESHOLD = 0.06`, le relevé est jugé trop lisse pour
être du LiDAR et le secteur est **non éligible** : ni la feature ni l'anneau
n'apparaissent, et le journal de préparation + le rapport MLL l'indiquent
explicitement. Seuil calibré sur 4 secteurs Barrois connus-LiDAR (0,1221 à
0,1407 mesuré, largement au-dessus du seuil).

**Validation (2026-07-27/28, Barrois, 4 secteurs contre l'inventaire ASHM)** :
AUC 0,62 à 0,81 selon secteur/rayon. Stable au changement de fenêtre
(0,72-0,74), résiste au découpage par canopée (0,676 sous canopée / 0,816 à
découvert — donc pas un artefact de visibilité comme le signal ponctuel).

> ⚠️ **Ce signal n'est PAS universel — testé et invalidé sur 2 domaines de
> karst à nu.** Contrairement au signal ponctuel (informatif partout où il est
> mesuré), l'intégration au score a été testée domaine par domaine par
> ablation contrôlée (même jeu de secteurs, avec/sans `rge_contrast_m`, gain
> vérifié secteur par secteur, pas seulement en moyenne — voir §4.3 pour la
> méthode). **Barrois** : gain net **+0,0089**, positif sur les 4/4 secteurs
> → intégré. **Lot** (karst à nu, causses) : gain net **-0,0151**, dégradé sur
> 2/4 secteurs → non intégré. **Jura plateau** (karst à nu) : gain net
> **-0,0015**, négligeable/mixte → non intégré. Hypothèse retenue : le signal
> capte un affaissement de surface qui n'existe que sous **couverture
> sédimentaire** (le relief du soutirage y est masqué, donc un LiDAR ancien
> peut le rater et un LiDAR récent le révéler) ; un **karst à nu** exprime déjà
> pleinement sa morphologie en surface, il n'y a rien à « découvrir » par
> différence temporelle. Détail complet : `docs/JOURNAL_EXPERIENCES.md`.
> Conséquence pratique : le paramètre `SIGNAL_RGEALTI` reste disponible partout
> (informatif même hors Barrois — l'anneau et la colonne sont produits dès que
> le secteur est éligible), mais il **ne contribue au score que via un modèle
> qui l'inclut dans ses `features`** — aujourd'hui uniquement `barrois_model`.

---

## 3. Scoring en mode exploratoire (hors modèle) — barème Bloc A v2

Quand aucun modèle validé ne s'applique au domaine, KarstPro utilise un **barème
morphologique à poids fixes**, dit *exploratoire*. Configuration intégrale :
`config/default_scoring.json` (`_version: 2.0`).

### 3.1 Seuils de priorité

| Priorité | Seuil de score | Couleur |
|---|---|---|
| **P1** | **≥ 55** | rouge |
| **P2** | **35 – 54** | orange |
| **P3** | **25 – 34** | jaune |
| hors-seuil | < 25 | gris |

Seuils **recalibrés en v2** après validation IKARRE (130 cavités,
Trois-Fontaines / Sommelonne / Ancerville) : abaissés d'environ 10 points pour
compenser le retrait de 3 composantes (voir §3.3).

### 3.2 Composantes **actives** et leur barème

Le score est la somme des composantes (clippé à 100). Chaque composante est une
fonction en escalier (seuils → points).

| Composante | Poids max | Seuils | Points | Sens |
|---|---|---|---|---|
| **Profondeur (m)** | **30** | 0,3 / 1 / 3 / 8 | 1 / 6 / 13 / 22 | + **continu** au-delà de 8 m : **+0,4 pt/m**, plafond 30 |
| **Contact géologique** | **25** | gradient exponentiel, decay **250 m** | × facteur karstifiabilité | proximité d'un contact karstifiable |
| **Pente de bord (°)** | **20** | 20 / 45 / 70 | 0 / 5 / 12 / 20 | soutirage actif / effondrement récent |
| **Absorption (bassin D8, m²)** | **18** | 1000 / 5000 / 20000 | 0 / 6 / 12 / 18 | capacité de perte hydraulique |
| **Surface (m²)** | **10** | 50 / 300 / 1500 | 2 / 5 / 8 / 10 | taille de l'impluvium |
| **Ratio P/√S** | **8** | 0,1 / 0,2 / 0,4 | 0 / 3 / 6 / 8 | verticalité (cuvette plate vs puits) |
| **TPI 500 m** | **8** | −20 / 0 / 20 | 0 / 3 / 5 / 8 | position sommitale = absorption directe |
| **Liseré** (bonus) | **+10** | rayon 100 m, ≥ 3 dolines alignées, écart-type ≤ 20° | bonus si vrai | alignement structural (karst de contact) |

**Karstifiabilité par NOTATION (facteur multiplicatif 0–1 du contact géologique)** —
préfixe de NOTATION BD Charm-50 (stable entre feuilles, contrairement à CODE_LEG) :

| Lithologie (préfixe) | Facteur |
|---|---|
| Jurassique j1–j3 | 0,9 |
| Jurassique j4–j9 (calcaires) | **1,0** |
| Craie c1–c5 (campanienne) | 0,4 – 0,5 |
| Craie c6–c7 | 0,3 |
| Éocène `e` | 0,7 |
| Tertiaire `t` | 0,6 |
| défaut (NOTATION absente) | 1,0 |

### 3.3 Composantes **désactivées** (informatives, poids 0)

Calculées et exposées (GPKG, prompt MLL) mais **non comptées** dans le score,
après la *ScoringReview 2026* :

| Composante | Pourquoi retirée |
|---|---|
| `circularité` | pénalisait les dolines structurales **allongées** du Barrois |
| `densité_500m` | ne discrimine plus en Barrois dense (> 50 voisines = 15 pts pour tout le monde) |

### 3.4 Statut honnête de ce barème

**Ces poids sont un *a priori* d'expert, pas un résultat optimisé sur données.**
L'ordre (profondeur > géologie > pente) repose sur la géomorphologie karstique ;
les valeurs précises sont arbitraires à ± quelques points. **Hors-échantillon,
ce barème classe à peine mieux que le hasard (AUC ≈ 0,57).** Il ne sert que de
hiérarchisation grossière **là où aucun modèle validé n'existe**. Dès qu'un
inventaire permet d'apprendre, ce ne sont plus ces poids qui pilotent la
priorité (voir §4).

> Le **Bloc B positionnel** (distance au réseau connu) existe encore dans le
> JSON pour compatibilité mais **n'est plus utilisé** : il pénalisait activement
> les zones vierges — exactement celles qu'on cherche à prospecter — et son
> score médian sur les cavités connues n'était que 5,2/100. Supprimé après
> validation IKARRE.

---

## 4. Le modèle appris du Barrois — validation, AUC, tentatives, impact

### 4.1 Pourquoi un modèle appris

La validation a montré que les poids manuels ne généralisent pas (§3.4). Mais le
**signal existe dans les données** : il fallait laisser les données fixer les
poids plutôt que l'intuition. D'où une **régression logistique par domaine
géologique**, entraînée sur des cavités réelles, et surtout **validée sur des
communes jamais vues**.

### 4.2 Anatomie du modèle (`models/barrois_model.json`)

- **Type** : régression logistique (sortie = probabilité calibrée 0–1).
- **8 variables historiques** (avec leur transformation, coefficients du modèle
  d'origine avant l'ajout du signal RGE ALTI) :

| Variable | Transfo | Coefficient appris | Lecture |
|---|---|---|---|
| `ratio_ps` (P/√S) | linéaire | **+0,517** | **plus fort prédicteur** : la verticalité compte |
| `circularité` | linéaire | +0,407 | formes compactes favorisées, de très près derrière |
| `surface_m2` | log | +0,308 | impluvium plus grand = mieux |
| `profondeur_m` | linéaire | +0,213 | plus profond = mieux |
| `bassin_versant_m2` | log | −0,074 | quasi nul |
| `comp_geologie_dist_m` | log | −0,156 | plus loin du contact = moins bien |
| `lisere` | linéaire | −0,227 | **contre-intuitif** : négatif ici |
| `pente_max_bord` | linéaire | **−0,299** | **contredit le barème manuel** (où la pente vaut +20) |

> **9ᵉ variable ajoutée en v1.11.0 : `rge_contrast_m`** (§2.5), coefficient
> **−0,258** dans le modèle actuellement déployé — cohérent avec le signal
> recherché : un `rge_contrast_m` plus négatif (affaissement plus marqué)
> augmente la probabilité prédite. Le réentraînement complet a légèrement fait
> bouger les 8 coefficients historiques ci-dessus (nouveau jeu d'entraînement,
> cf. §4.3) ; valeurs exactes à jour dans `models/barrois_model.json` plutôt
> que dans cette table, qui documente la lecture qualitative d'origine.

> **Point honnête et frappant à présenter :** sur la pente de bord et le liseré,
> le modèle appris **contredit le barème manuel**. Là où l'intuition donnait +20
> points à une pente raide, les données du Barrois lui attribuent un coefficient
> **négatif**. C'est exactement la raison d'être de l'apprentissage : corriger
> les *a priori* faux.

- **Pipeline d'inférence (pur numpy)** : pour chaque doline → transfo log/linéaire
  → imputation des manquants par la **médiane** du modèle → standardisation
  `(x − scaler_mean) / scaler_scale` → produit scalaire avec les coefficients +
  intercept (−0,322) → sigmoïde → probabilité.
- **Seuils de probabilité calibrés** : P1 ≥ **0,840**, P2 ≥ **0,628**, P3 ≥
  **0,472**. Le `score_ml` affiché = probabilité × 100.

### 4.3 Processus de validation (le cœur de la rigueur)

**Deux niveaux, du plus optimiste au plus honnête :**

1. **LOCO-CV (Leave-One-Commune-Out)** sur les 4 communes d'entraînement
   (Ancerville, Lisle-en-Rigault, Sommelonne, Trois-Fontaines) : on retire une
   commune entière, on entraîne sur les autres, on teste sur la retirée.
   **AUC LOCO moyen = 0,716.** *Mais* : ces communes ont servi à régler l'outil →
   chiffre optimiste par construction.

2. **Validation hors-échantillon contre inventaire indépendant (GERSM)** sur
   **2 communes jamais vues** — le vrai test (`validation/inventaire/`) :

| Commune | n positifs (gouffre strict) | **AUC modèle** | AUC barème manuel |
|---|---|---|---|
| Beurey-sur-Saulx | 155 | **0,65** | 0,57 |
| Robert-Espagne | 104 | **0,72** | 0,57 |

**Protocole d'étiquetage** (rayon 50 m) :
- **positif** : une entrée **stricte** (gouffre pénétrable) de l'inventaire à ≤ 50 m ;
- **négatif** : **aucune** entrée (de quelque type) à ≤ 50 m ;
- **ambigu** (exclu) : pas de gouffre, mais une entrée de soutirage proche — exclu
  pour ne pas compter à tort un vrai négatif.

**Garde anti-circularité** : le script **refuse** de valider sur une commune
d'entraînement, et l'inventaire de validation (GERSM) est **disjoint** de la
source qui sert à apparier les cavités dans le pipeline (Géorisques). Sans ces
deux garanties, le chiffre serait flatteur et sans valeur.

**Conclusion validée par les données** : sur commune neuve, +0,10 à +0,15 d'AUC
de façon stable sur deux communes indépendantes → l'intégration du modèle est
**justifiée empiriquement**, pas par conviction.

### 4.4 Ce qu'est l'AUC (et pourquoi c'est la bonne métrique ici)

L'**AUC** (*Area Under the ROC Curve*) mesure la capacité à **classer** : c'est la
probabilité qu'une vraie cavité tirée au hasard reçoive un score supérieur à un
non-cavité tiré au hasard.
- **0,5 = hasard** ; **1,0 = classement parfait** ; 0,65–0,72 = signal modéré mais réel.
- On la préfère au « taux de bonnes détections » car les classes sont **très
  déséquilibrées** (peu de cavités, beaucoup de dolines) et parce que l'usage
  réel est un **classement** : on prospecte les mieux classées d'abord. L'AUC est
  insensible au choix du seuil, contrairement à la précision/rappel.

### 4.5 Ce qui a été tenté pour augmenter l'AUC (et l'impact)

Toutes les pistes ci-dessous ont été testées et **documentées comme négatives**
(honnêteté scientifique — on publie aussi ce qui ne marche pas) :

| Piste testée | Résultat |
|---|---|
| **Failles BRGM** (proximité) | aucun gain |
| **Linéaments LiDAR** (extraction automatique) | aucun gain |
| **Développement des cavités connues** | aucun gain |
| **Hydrologie des thalwegs secs** | aucun gain |
| **Ré-entraînement sur jeu élargi** (BaseKarst52) | LOCO flatté à 0,752, mais communes neuves **inchangées** (Beurey 0,675 / Robert 0,59) : pas de gain hors-domaine |
| **Bloc B positionnel** (distance au réseau) | **retiré** : pénalisait les zones vierges, médiane 5,2/100 |
| Composantes redondantes (circularité / densité) | **retirées** du score |

Ce qui a, en revanche, **amélioré** le scoring :
- passage de la **profondeur en continu** au-delà de 8 m (avant, un gouffre de 8 m
  et un de 20 m avaient le même score) ;
- ajout du **TPI 500 m** terrain réel (image intégrale) au lieu du proxy
  « dolines voisines » ;
- surtout, le **passage des poids manuels au modèle appris** : +0,10 à +0,15 d'AUC.

**Le plafond** : l'AUC plafonne autour de **0,65 par domaine**. C'est une **limite
physique**, pas algorithmique — *la forme d'une doline en surface prédit faiblement
le vide qu'il y a dessous*. Aucune des variables de surface testées ne franchit ce
plafond ; le gain de l'outil n'est donc **pas** dans une AUC toujours plus haute,
mais (a) dans le **classement** (concentration des cibles d'un facteur ~1,5–2) et
(b) dans la **couverture** (un domaine validé de plus à chaque inventaire).

### 4.6 Impact concret sur le scoring

- **Quand le modèle s'applique** (domaine reconnu — voir §5) : la priorité P1/P2/P3
  vient de la **probabilité** du modèle (seuils 0,842 / 0,624 / 0,473), pas du
  barème. `score_ml` est renseigné.
- **Sinon** : barème manuel exploratoire (§3), `score_ml = NaN`.
- **Ce que le modèle améliore vraiment** : le **rang**, pas mécaniquement le taux
  de touche absolu au sommet. La **précision@P1 (3–10 %)** est une **borne basse** :
  une doline P1 sans cavité connue à 50 m peut être une **découverte** (inventaire
  incomplet), pas un faux positif.

---

## 5. Routeur multi-modèles — quand le modèle s'applique

Le routeur sélectionne automatiquement le bon modèle (ou retombe sur le barème)
selon trois critères, sans jamais appliquer un modèle hors de son domaine :

1. **Lithologie** : ≥ **50 %** des dolines sur les faciès du domaine
   (`domain_notations` Barrois = `n4, n3, j7, j6` ; préfixe NOTATION) ;
2. **Distance géographique** : avertissement au-delà de **40 km** du centroïde du
   domaine, **veto dur** au-delà de **120 km** ;
3. **Veto** : hors de ces bornes → poids manuels exploratoires.

> ⚠️ **Être dans la région Barrois ne suffit pas.** Le critère n°1 porte sur la
> lithologie *réellement sous les dolines*, pas sur une appartenance
> géographique/administrative au Barrois. Cas réel observé : une petite
> emprise de test en Haute-Marne, à ~23 km du centroïde du domaine (donc bien
> sous le seuil d'alerte de 40 km), a été rejetée par le routeur — 215 de ses
> 223 dolines (96 %) tombaient sur la formation **n2** (sables et grès,
> Valanginien, non calcaire), et seulement 4 (2 %) sur **j7c** (calcaire,
> préfixe attendu). Le log affiche alors *« Aucun des 5 modèle(s) de domaine
> ne correspond à cette zone »* et le score retombe sur les poids manuels
> exploratoires (`score_ml` = `NaN` pour toutes les dolines). Ce n'est pas un
> bug : appliquer un modèle entraîné sur du calcaire karstifiable à une
> emprise essentiellement gréseuse produirait des prédictions sans fondement.
> Une emprise plus large, couvrant plus de faciès j7/n3/n4, repasserait
> probablement le seuil de 50 %.

| Modèle | Domaine | AUC | Application |
|---|---|---|---|
| **Barrois** | Meuse / Haute-Marne (karst sous couverture) | 0,65–0,72 hors-échantillon | **automatique** |
| **Jura plateau** | Doubs / Jura (karst nu à gouffres) | 0,633 LOCO (5 communes) | **opt-in** (manuel) |
| **Lot** | Causses du Quercy | 0,602 LOCO (8 communes) | **opt-in** (manuel) |
| **Dordogne** | Périgord noir | 0,629 LOCO (8 communes) | **opt-in** (manuel) |
| **Ardèche** | Gorges de l'Ardèche / Bas-Vivarais | 0,638 LOCO (8 communes) | **opt-in** (manuel) |

> Le Jura plateau est en **opt-in** par honnêteté : un plateau et une
> vallée/reculée jurassiens ont la **même lithologie** ; aucun descripteur du MNT
> ne sépare de façon fiable les deux régimes (les dolines ont des formes
> identiques). La machine ne prétend donc pas savoir où le modèle est valide —
> c'est le spéléologue qui l'active, sur son jugement géologique.
>
> Les trois modèles Lot/Dordogne/Ardèche sont **opt-in** pour une autre raison :
> le BD Charm-50 (lithologie fine, colonne `NOTATION`) n'est mis en cache que
> pour la Bourgogne-Franche-Comté et le Grand-Est. Hors de ce cache, KarstPro
> retombe sur le WFS BRGM `LITHO_1M` (1/1 000 000, un seul polygone générique
> par commune, sans colonne `NOTATION`) — trop grossier pour construire une
> signature lithologique (`domain_notations` vide). Ces modèles ne peuvent donc
> pas être suggérés automatiquement par lithologie ; seule la distance
> géographique (et le veto à 120 km) s'applique en repli, ou l'activation
> manuelle par l'utilisateur.

---

## 5bis. Territoires et capacités — France / Espagne

Depuis le 2026-08-02, le routage multi-pays repose sur un modèle
**territoires / capacités** (`karstpro/core/territoires/`), qui remplace le
routeur précédent (`core/country_router.py`, supprimé). Conception complète :
`docs/superpowers/specs/2026-08-02-architecture-territoires-capacites-design.md`.

### Le principe

Le pipeline (`karst_prep_algorithm.py`) ne nomme jamais un territoire. Il
nomme des **besoins** — les douze *capacités* ci-dessous — et interroge le
territoire choisi pour savoir comment chacune est satisfaite :

```python
cap = territoire.capacite("contexte_karstique")
if cap.absente:
    feedback.pushInfo(cap.raison)
else:
    cap.executer(ctx)
```

Un territoire (`france`, `espagne`, menu déroulant `PAYS`, choisi
explicitement — jamais détecté depuis la bbox, cf. historique ci-dessous)
déclare chacune des douze capacités sous l'une de trois formes :

- un **fournisseur déclaratif** — une entrée de config JSON (URL, couche,
  CRS, format) consommée par un client générique ;
- un **adaptateur** — un module de code, pour ce qui a du contrôle de flux ;
- une **absence explicite** (`{"type": "absente", "raison": "..."}`), qui
  porte le message montré à l'utilisateur.

### Les douze capacités

| Capacité | France | Espagne | Forme (FR / ES) |
|---|---|---|---|
| `crs_travail` | EPSG:2154 (Lambert-93) | UTM 29/30/31 selon la longitude du centroïde de la bbox | config / config |
| `mnt` | LiDAR HD IGN (WFS + téléchargement COPC + PDAL) | LiDAR PNOA 1 m automatique → repli MDT WCS 5 m | adaptateur / chaîne |
| `geologie` | BD Charm-50 (cache local) + repli WFS BRGM | IGME ArcGIS REST (1:50 000 → repli 1:1M) | adaptateur / config |
| `contexte_karstique` | BDLISA (vérification zone karstique) | **absente** | config / absente |
| `cavites_connues` | Géorisques | **absente** | config / absente |
| `obstacles_gouffres` | BD Topo bâti/eau | SIOSE — INSPIRE Land Cover (bâti, eau) | adaptateur / adaptateur |
| `vegetation_gouffres` | BD Topo végétation | SIOSE — INSPIRE Land Cover (végétation) | adaptateur / adaptateur |
| `anthropique_dolines` | BD Topo carrières (filtre) | **absente** | config / absente |
| `affaissement_historique` | Signal RGE ALTI | **absente** | adaptateur / absente |
| `modele_appris` | Modèles Barrois/Jura/Lot/Dordogne/Ardèche (§5) | **absente** — scoring exploratoire seul | config / absente |
| `fonds_carte` | Ortho IGN + SCAN25 (clé perso) + Plan IGN | Ortho PNOA + MTN raster + IGN Base (WMS INSPIRE) | config / config |
| `points_eau_karstiques` | BD Topo (sources, pertes, résurgences) | **absente** | adaptateur / absente |

Côté France, six capacités sont déclaratives (URL/couche/CRS suffisent) et six
exigent un adaptateur en code : `mnt`, `geologie`, `obstacles_gouffres`,
`vegetation_gouffres`, `affaissement_historique` et `points_eau_karstiques`.
Côté Espagne, quatre sont déclaratives, deux sont des adaptateurs (le filtrage
SIOSE des gouffres) et six sont absentes.

Les six capacités absentes en Espagne portent un message qui explique, dans
le journal d'exécution, ce qui n'est pas fait et pourquoi (ex. « Géorisques
(base française) non applicable hors de France — import ignoré »), au lieu de
laisser un service français interrogé en
silence sur une bbox hors de son domaine — c'est exactement le mode de
panne qui a produit les bugs du 2026-08-02 (BDLISA appelée avec une
conversion Lambert-93 codée en dur sur des coordonnées espagnoles, BD Topo
renvoyant une requête vide silencieuse).

### La frontière config / code

> **Config** = ce qu'un client générique sait consommer : URL, couche,
> CRS, format, correspondance de champs. **Code** = tout ce qui a du
> contrôle de flux : enchaînement, pagination, expression régulière, repli
> conditionnel, pipeline PDAL.

Cette frontière n'est pas un choix esthétique : mesuré sur le code réel,
**quatre protocoles différents pour deux territoires seulement** —

| Capacité | France | Espagne |
|---|---|---|
| MNT | WFS + téléchargement COPC + PDAL | scraping HTML, 3 POST enchaînés, regex, codes INE |
| MNT (repli) | — | WCS 2.0.1 |
| Géologie | WFS + GeoPackages locaux embarqués | ArcGIS REST |
| Fonds de carte | WMS + WMTS | WMS |

— aucune config ne les exprimerait sans réinventer un langage de
programmation en JSON. `core/lidar_pnoa_auto.py`, l'adaptateur `mnt_pnoa`,
fait à lui seul **442 lignes** : pagination du listing par commune,
extraction de `sec=<id>` par expression régulière, deux requêtes POST
chaînées (`initDescargaDir` puis `descargaDir`), cache par cellule de
grille 1×1 km, en-têtes HTTP imitant un navigateur (nécessaires : le WAF du
portail bloque sur la signature de la requête, pas sur l'IP — incident du
2026-08-02, `docs/JOURNAL_EXPERIENCES.md`). Ces 442 lignes sont
irréductibles ; c'est ce chiffre qui a tranché contre l'option « tout en
config ».

À l'inverse, la config apporte un bénéfice réel et mesuré : les quatre
fonctions de fond de carte (ortho IGN, SCAN25, Plan IGN, ortho PNOA)
fusionnent en un seul client générique piloté par déclaration, et le bug du
2026-08-02 (`"EPSG:25830".startswith("EPSG:2582")` faux, branche espagnole
inatteignable pour les zones 30/31) devient **inexprimable** : il n'y a
plus de branche par CRS écrite à la main, seulement une table explicite
zone → code EPSG (`crs_travail` de `espagne.json`, ci-dessous). Aucune
fabrication de code EPSG par concaténation n'est permise dans le modèle.

```json
"crs_travail": {
  "type": "utm_par_longitude",
  "zones": {"29": "EPSG:25829", "30": "EPSG:25830", "31": "EPSG:25831"}
}
```

### Le contrôle d'exhaustivité

La clé de voûte du modèle : un territoire mal déclaré **refuse d'exister**,
plutôt que de laisser un oubli passer inaperçu jusqu'à un lancement réel
(le mode de panne qui a produit les trois bugs France-only du 2026-08-02).
À la construction de chaque `Territoire` (`karstpro/core/territoires/registre.py`) :

- une capacité de la liste figée manquante lève `ConfigurationIncomplete` ;
- une capacité hors de la liste figée (faute de frappe, ex.
  `vegetation_gouffre` sans le `s` final) lève `ConfigurationInconnue` —
  sans ce contrôle, la faute de frappe passerait pour une déclaration
  valide tout en laissant la vraie capacité manquante ;
- `crs_travail` ou `mnt` déclarée absente lève `ConfigurationInvalide` : ce
  sont les deux seules capacités sans lesquelles le pipeline n'a aucun
  sens.

Un test parcourt tous les territoires × toutes les capacités : ajouter une
capacité à la liste figée fait échouer immédiatement tout territoire
incomplet, en test, avant tout lancement. Le chargement des fichiers JSON
(`karstpro/core/territoires/chargeur.py`) applique le même principe côté
schéma : type de fournisseur inconnu, champ obligatoire manquant ou
adaptateur inexistant lèvent au chargement, avec le fichier et la clé
fautive dans le message — jamais un mode de panne silencieux plus loin
dans le pipeline.

### Historique de la décision — pourquoi un menu et pas une détection automatique par bbox

La conception initiale (routeur précédent) déduisait le pays des
coordonnées de la zone d'étude. Abandonnée en cours d'implémentation : les
rectangles d'emprise France/Espagne se chevauchent sur la côte cantabrique
(le rectangle France, dimensionné pour couvrir Ouessant en Bretagne, déborde
jusqu'en Espagne du Nord) — raffiner indéfiniment des polygones d'emprise
n'aurait fait que déplacer le problème. Le paramètre `PAYS` reste donc un
menu déroulant explicite (« France » par défaut), jamais une détection.

### Détails opérationnels par capacité

**Géologie Espagne — IGME (`core/geology_igme.py`).** Même patron à deux
niveaux que le BRGM (§5) : local d'abord, repli national si vide.

| Niveau | Service | URL |
|---|---|---|
| 1:50 000 (local) | `IGME_Geode_50`, layer 8 « Recintos geología » | `https://mapas.igme.es/gis/rest/services/Cartografia_Geologica/IGME_Geode_50/MapServer/8/query` |
| 1:1 000 000 (repli national) | `IGME_Litologias_1M` | `https://mapas.igme.es/gis/rest/services/Cartografia_Geologica/IGME_Litologias_1M/MapServer/0/query` |

Réponse ArcGIS REST JSON (`features[].attributes.Litologia` en texte libre
espagnol). La karstifiabilité (0–1) est déduite par recherche de
sous-chaîne (`caliza` → 1.0, `dolom` → 0.9, `yeso` → 0.7, `marga` → 0.4,
`arenisca` → 0.3, `arcilla` → 0.1, sinon 0.5 par défaut) — une
approximation de départ par analogie avec la table NOTATION du BD
Charm-50, pas une vérité géologique établie. ⚠️ Le segment `/rest/` est
obligatoire dans l'URL : une URL sans ce segment renvoie une page d'erreur
générique ArcGIS, pas du JSON.

**MNT Espagne — trois chemins, `MNT_FILES` (LAZ PNOA manuel, 1 m)
prioritaire, PNOA automatique (1 m) ensuite via l'adaptateur `mnt_pnoa`,
MDT WCS 5 m en dernier repli** (`Chaine` de `espagne.json`, §6.2 du design).
Le repli WCS (`https://servicios.idee.es/wcs-inspire/mdt`, WCS 2.0.1
INSPIRE) sert un GeoTIFF sol nu directement, sans LAZ ni PDAL, sur un
unique coverage `Elevacion25830_5` qui couvre à lui seul les trois fuseaux
UTM (l'IGN espagnol les a mosaïqués dans une grille 25830 unique — un
piège identifié en vérifiant `GetCapabilities`, l'hypothèse initiale d'un
coverage par fuseau était fausse). L'avertissement de résolution dégradée
n'apparaît que lorsque ce repli est effectivement emprunté. `download_pnoa_auto`
renvoie les tuiles téléchargées dès qu'**au moins une** a réussi (plus
tolérant que `download_lidar_tiles` côté France, qui lève au moindre échec)
— un MNT 1 m partiel reste préférable à jeter tout le résultat pour une
seule tuile en échec.

**CRS de travail.**

| Territoire | CRS | Calcul |
|---|---|---|
| France | `EPSG:2154` (Lambert-93) | fixe |
| Espagne | `EPSG:2582<zone>` (ETRS89/UTM) | zone UTM (29/30/31) déduite de la longitude du centroïde de la bbox, table explicite (pas de concaténation) |

Codes officiels espagnols (`EPSG:258XX`), pas `EPSG:326XX` WGS84-UTM, pour
rester cohérent avec le référentiel des données IGME. Une longitude hors
des zones 29/30/31 (Canaries, zone 28, référentiel différent) lève une
erreur explicite listant les zones couvertes.

> ⚠️ **Limites actuelles, à connaître avant usage :**
> - **Espagne continentale uniquement, zones UTM 29/30/31** — Canaries non gérées.
> - **Pas de modèle appris hors France** — scoring espagnol toujours exploratoire.
> - **Pas de signal RGE ALTI hors France** — produit IGN français sans équivalent branché.
> - **LiDAR PNOA : une seule campagne (2022-2025, `codSerie=LIDA3`)** — pas de
>   comparaison multi-campagnes façon RGE ALTI pour l'instant.
> - **Automatisation PNOA reposant sur un endpoint non documenté** — le
>   repli WCS existe précisément pour absorber une panne de ce mécanisme.
> - **Table de karstifiabilité IGME approximative**, cf. ci-dessus.

**Fond de carte satellite.** L'ortho PNOA (WMS INSPIRE
`www.ign.es/wms-inspire/pnoa-ma`, layer `OI.OrthoimageCoverage`) est ajoutée
au projet QGIS/QField généré, décochée par défaut — même patron que l'ortho
IGN française. SCAN25/Plan IGN restent France-only (produits IGN sans
équivalent espagnol branché) ; sans ortho, un projet Espagne n'avait
jusqu'ici que l'ombrage MNT comme repère visuel.

---

## 6. Diagnostic empirique de domaine — outil « Diagnostiquer un modèle »

Le routeur (§5) sait sélectionner un modèle **automatique** pour une zone déjà
validée, mais ne peut jamais dire, pour une commune **jamais vue**, si un
modèle opt-in (Jura plateau, Lot, Dordogne, Ardèche…) s'y appliquerait — ce
serait deviner le régime géologique à l'avance, **prouvé impossible** depuis
le relief seul (concept drift, cf. `docs/JOURNAL_EXPERIENCES.md` — 7 pistes
testées, 7 échecs).

**Ce qui change la donne : un inventaire même partiel.** Dès qu'une commune
cible a **quelques cavités déjà connues** (BRGM Géorisques, toujours
disponible, et/ou un inventaire utilisateur), la question n'est plus
« deviner » mais **mesurer** : `core/domain_diagnostic.py::diagnose_models`
applique chaque modèle disponible aux dolines déjà détectées, labellise
chaque doline (1 si une cavité connue est à ≤ `label_radius_m` du centroïde,
0 sinon — rayon **propre à chaque modèle**, pas un rayon global, pour rester
cohérent avec sa calibration d'entraînement), puis calcule l'AUC réel entre
ce label et la probabilité prédite par le modèle (`model_score.predict_proba`).

**AUC en numpy pur, jamais sklearn.** Comme l'inférence elle-même
(`core/model_score.py`), l'AUC est calculée par la statistique de
Mann-Whitney (rangs moyens en cas d'égalité), pas par
`sklearn.metrics.roc_auc_score` — le plugin distribué n'embarque ni sklearn
ni joblib. Une première version de l'outil violait cette règle par erreur
(import `sklearn` oublié) ; le bug a été trouvé et corrigé en 2026-07 grâce à
un test réel en QGIS, dont l'environnement Python n'a pas sklearn installé
contrairement à un environnement de développement.

**Validation de la méthode elle-même** (session 2026-07-06,
`prototypes/diagnose_domain.py`) : sur les 7 communes du Jura déjà étudiées,
l'AUC mesuré par ce diagnostic (modèle entraîné sur les 6 *autres* communes,
jamais la cible) tombe à **≤ 0,013 du LOCO complet** — dont 2 communes à
l'écart exact de 0,000. Le diagnostic reproduit donc fidèlement ce que donnerait
une vraie validation croisée, appliqué à une seule commune cible plutôt qu'à
tout un jeu d'entraînement.

**Interprétation du résultat** (seuils de `format_diagnostic_report`) :
AUC ≥ 0,60 → « s'applique bien » ; 0,55–0,60 → « s'applique faiblement » ;
< 0,55 → « ne s'applique pas ». En dessous de `MIN_CAVITES` cavités appariées
(défaut 10), l'AUC est quand même calculé mais signalé comme peu fiable.

> ⚠️ **Ne pas suivre la recommandation « meilleur modèle » les yeux fermés.**
> Un audit croisé (2026-07-07, `prototypes/diagnose_all_communes.py`) sur les
> 35 communes déjà préparées montre que le modèle du domicile géographique
> n'est le mieux classé que dans **46 % des cas** (rang moyen 1,83/5, contre
> 3,0 au hasard — un vrai signal existe, mais plus faible que la spécialisation
> régionale supposée par le routage lithologie/distance). Les 5 modèles
> partagent les mêmes 8 features morphométriques (une seule,
> `comp_geologie_dist_m`, touche vraiment la lithologie) : ils captent surtout
> « à quoi ressemble une doline plausible », pas une signature régionale
> forte. Le diagnostic mesure honnêtement l'AUC de chaque modèle disponible —
> à toi de juger si l'écart avec le modèle recommandé justifie de changer.

**Read-only.** Aucune couche n'est modifiée, aucun modèle n'est activé
automatiquement — le choix reste dans le menu « Priorisation » de
« Préparer une sortie », ou via « Forcer un modèle différent » (§ suivante
implicitement liée, voir le README pour l'usage pas à pas).

---

## 7. Cavités connues — rattachement `cavite_connue_proche`

Chaque doline reçoit un flag de proximité à une cavité déjà répertoriée (couche
utilisateur `cavites_connues` et/ou cavités BRGM Géorisques téléchargées
automatiquement), **purement informatif** (hors score, aucune suppression
automatique des cibles).

**Préférence inventaire.** Quand une cavité est trouvée dans le rayon, KarstPro
rattache en priorité une cavité de **l'inventaire utilisateur** (`cavites_connues`,
noms/références fiables) plutôt qu'une cavité Géorisques « anonyme » même
légèrement plus proche. Géorisques ne sert de repli que si aucune cavité
d'inventaire n'est à proximité. Les cavités Géorisques sont normalisées avant
la fusion (`nom_cavite → name`, `type_cavite → type`, `identifiant → reference`) ;
les colonnes acceptées côté couche utilisateur sont `name`, `type`, `date_disc`,
`date_expl`, `explorers`, `comment`, `reference` (colonnes absentes ignorées
silencieusement).

**Pourquoi 20 m.** Le rayon correspond à la marge d'erreur GPS + imprécision de
pointé sur une cavité ancienne. Dans un karst sous couverture (Barrois), deux
dolines à 25 m peuvent alimenter des conduits distincts : 20 m est volontairement
conservateur pour ne pas masquer des cibles légitimes dans les alignements
denses — un rayon plus large rattacherait à tort des dolines indépendantes à
une même cavité.

**Pourquoi le nom n'est rempli que si la cavité est proche.** `cavite_distance_m`
est toujours renseignée (loin de tout = territoire vierge), mais `cavite_nom` /
`cavite_type` / `cavite_ref` restent vides au-delà de 20 m : sans cette limite,
une doline à 1 km d'une cavité « référencerait » celle-ci dans l'interface,
ce qui prête à confusion sur un rattachement qui n'a pas de sens physique.

**Pourquoi aucune suppression automatique.** Une doline proche d'une cavité
connue reste dans les cibles P1/P2/P3 (signalée 🏛️ dans le rapport MLL) : la
cavité peut être peu ou anciennement explorée, ou correspondre à une entrée
distincte du même réseau. Décider si elle vaut encore une visite est un
jugement de terrain, pas une règle géométrique fiable à automatiser.

---

## 8. Données injectées dans l'export MLL — quoi et d'où

L'export MLL (« Modèle de Langage ») produit **un fichier texte unique** (le
*prompt*) destiné à une analyse par IA. Il n'envoie **jamais** de données brutes
LiDAR : il assemble des données déjà calculées + le contexte cartographique. Voici
l'intégralité de ce qui le compose et sa provenance.

| Bloc injecté dans le prompt | Contenu | Provenance |
|---|---|---|
| **Dolines scorées** (P1+P2+P3, JSON ≤ 300) | morphométrie + score + coords | couche `dolines` du GeoPackage de préparation (lue en SQL direct) |
| **Cavités connues** | nom, type, dates, explorateurs, référence | inventaire **Karst Entry** de l'utilisateur (gpkg), **filtré sur la box d'étude** |
| **Cavités Géorisques** | nom, type, identifiant BRGM, repérage | **BRGM Géorisques** (BD Cavités nationale), récupéré pendant la préparation → couche `cavites_georisques` |
| **Traçages hydrologiques** | injection → résurgence, colorant, résultat, temps de transit, coords L93 | inventaire **Traçages Karst Entry**, filtré bbox (si source L93) |
| **Gouffres détectés** | Ø, compacité, distance à la cible | couche `gouffres` (détection des vides LiDAR), **ceux proches d'une cible ≤ 100 m** |
| **Points d'eau** | type, toponyme, distance à la cible | couche `bdtopo_eau` — **BD Topo** (Géoplateforme), sources / pertes référencées |
| **Clusters géographiques** | regroupements rayon 400 m | **calculé à l'export** (centroïdes des cibles rouges + oranges) |
| **Pendage / sens de drainage** | direction | **estimé automatiquement** (contacts géologiques + MNT) ou saisi par l'utilisateur |
| **Contexte terrain / zones exclues** | texte libre | **saisi par l'utilisateur** (nettoyé du HTML avant injection) |
| **Moteur de scoring** | modèle appris vs barème | déterminé à l'export selon la présence de `score_ml` |

### 7.1 Détail des attributs de doline et leur origine

Chaque doline du JSON porte ses attributs, eux-mêmes issus de plusieurs sources
en amont (calculés à la **préparation**, pas à l'export) :

| Attribut | Origine |
|---|---|
| `surface_m2`, `profondeur_m`, `altitude_m`, `pente_max_bord`, `ratio_ps`, `tpi_500m`, `lisere` | **MNT LiDAR HD IGN 1 m** (morphométrie) |
| `bassin_versant_m2`, `type_doline` | **flux D8** (WhiteboxTools) sur le MNT |
| `comp_geologie`, `comp_geologie_dist_m` | **BD Charm-50 BRGM** (contact karstifiable) |
| `cavite_connue_proche` | proximité à l'**inventaire** (utilisateur + Géorisques) |
| `score`, `score_morpho`, `score_ml`, `priorite` | **scoring** (barème §3 ou modèle §4) |
| `x_l93`, `y_l93`, `lat_wgs84`, `lon_wgs84` | coordonnées, **WGS84 pré-calculé côté plugin** |

### 7.2 Garde-fous sur les données injectées

- **Coordonnées WGS84 pré-calculées** : le prompt fournit le lat/lon exact ; le
  LLM a la consigne explicite de **ne jamais reprojeter lui-même** (une erreur de
  projection enverrait l'opérateur au mauvais endroit).
- **Inventaire filtré sur l'emprise** : un inventaire départemental n'injecte que
  les cavités/traçages **dans la box d'étude** (filtre conscient du CRS : gère un
  inventaire stocké en WGS84).
- **JSON borné** : seules P1+P2+P3 (plafond 300 meilleures P2/P3) ; les dolines
  **grises** (hors-seuil) sont exclues — elles feraient déborder la fenêtre de
  contexte du LLM sans valeur de prospection.
- **Champs texte assainis** : tout commentaire d'inventaire est nettoyé (retrait
  de résidus HTML/Office) avant injection.

### 7.3 Ce qui n'est **pas** envoyé

Le nuage de points LiDAR brut, le MNT raster, les géométries complètes des
polygones (seuls les **centroïdes** sont transmis), et les dolines grises. Le
prompt est une **synthèse géoréférencée**, pas un dépôt de données.

---

## 9. Synthèse — limites assumées

- La détection trouve des **formes**, pas des cavités : la vérification terrain
  reste indispensable.
- **~18 %** des cavités d'inventaire restent **hors-seuil** quel que soit le
  réglage (entrée ponctuelle, remplissage, épikarst) : **limite physique** du
  MNT 1 m, pas un défaut de l'outil.
- L'AUC **plafonne ~0,65 par domaine** : la morphologie de surface prédit
  faiblement le vide souterrain.
- La généralisation du modèle **s'arrête à la frontière géologique** : hors
  domaine validé, retour au barème exploratoire — et l'outil le **dit**.
- Les gouffres **noyés / aménagés / sous canopée dense** échappent à la détection
  morphologique (référencement BD Topo en complément, pas découverte).

**Ligne directrice :** KarstPro **priorise**, il ne décide pas. Sa valeur n'est
pas dans une AUC parfaite mais dans un classement reproductible, sans biais
d'exploration, qui concentre l'effort de prospection — et qui dit honnêtement
où il sait et où il ne sait pas.

---

## Annexe A — Configuration de scoring (source de vérité)

Contenu **intégral et commenté** de `karstpro/config/default_scoring.json`,
**injecté automatiquement** à la génération du PDF (jamais recopié à la main → ne
peut pas diverger du code). Les clés `_note` / `_legende_format` / `_…` sont des
commentaires (ignorés par le moteur de scoring) qui décrivent chaque valeur. Les
longues lignes sont repliées pour tenir dans la page.

<!--INJECT:default_scoring-->
