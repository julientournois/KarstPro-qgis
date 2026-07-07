# Changelog — KarstPro

Évolutions notables du plugin. Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/),
versionnage sémantique. Les paquets distribués sont nommés `KarstPro_v<version>_<date>.zip`.

## [1.6.0] — 2026-07-08

### Ajouté
- **Nouvel outil « Diagnostiquer un modèle ».** Applique chaque modèle appris
  disponible (Barrois, Jura plateau…) aux dolines déjà détectées d'une
  commune et mesure l'AUC réel contre un inventaire de cavités connues
  fourni par l'utilisateur — même partiel. Ne prédit rien (deviner le
  régime géologique sans cavités connues est impossible, cf.
  `docs/JOURNAL_EXPERIENCES.md`) : vérifie empiriquement si un modèle
  s'applique, sans jamais l'activer automatiquement (le choix reste dans
  le menu « Priorisation »). Read-only, aucune couche modifiée. La couche
  `cavites_georisques` (BRGM, publique, déjà téléchargée à la préparation)
  est utilisée automatiquement en complément de l'inventaire fourni, ou
  seule si aucun inventaire personnel n'est donné — permet de tester un
  modèle même sans inventaire privé.
- **« Refaire une étude » : nouveau paramètre avancé « Forcer un modèle
  différent ».** Permet de re-scorer une étude déjà préparée avec un autre
  modèle que celui utilisé à l'origine (utile si un modèle plus récent ou
  mieux adapté est disponible). Les dolines détectées ne changent pas ;
  seule leur priorité (couleur) peut changer, uniquement pour celles jamais
  visitées — les verdicts terrain déjà saisis sont protégés (report par
  position, jamais par référence au score). Le journal indique combien de
  dolines changent de palier de priorité.
- **Trois nouveaux modèles régionaux opt-in : Lot (Causses du Quercy),
  Dordogne (Périgord noir), Ardèche (Gorges de l'Ardèche / Bas-Vivarais).**
  Entraînés en LOCO sur 8 communes chacun, à partir des cavités BRGM
  Géorisques (données publiques). AUC hors-échantillon honnêtes : Ardèche
  0,638, Dordogne 0,629, Lot 0,602 (aucune commune exclue — voir la leçon
  méthodologique dans `docs/JOURNAL_EXPERIENCES.md` sur pourquoi deux
  exclusions initiales injustifiées ont été annulées). Activables via
  « Forcer un modèle différent » (voir ci-dessus) ou directement à la
  préparation ; jamais sélectionnés automatiquement, faute de lithologie
  fine (BD Charm-50) disponible sur ces départements.

### Corrigé
- **« Diagnostiquer un modèle » plantait à l'usage réel (dépendance sklearn
  manquante).** Le calcul d'AUC importait `sklearn.metrics.roc_auc_score` au
  runtime, alors que le plugin distribué n'embarque ni sklearn ni joblib
  (convention documentée dans `core/model_score.py`) — trouvé au premier vrai
  clic dans QGIS (smoke test headless), aurait échoué avec
  `ModuleNotFoundError` chez l'utilisateur. Remplacé par un calcul d'AUC en
  numpy pur (statistique de Mann-Whitney, rangs moyens), vérifié identique.
- **README : estimation du temps de préparation corrigée (était fausse pour
  les grandes zones).** « 5–20 min selon la surface » sous-estimait largement
  les grandes emprises : mesuré sur 31 préparations réelles de cette session,
  Poligny (151 km²) a pris 103 min, Gramat (121 km²) 92 min. Remplacé par une
  estimation basée sur ces mesures (~35–37 s/km², dominé par le
  téléchargement LiDAR) ; ajouté aussi le temps réel de « Refaire une étude »
  avec cache (1–2 min, indépendant de la surface).
- **« Refaire une étude » + modèle forcé : le résumé de changement de palier
  ne s'affichait jamais, en silence.** Le code cherchait une colonne `name`
  sur la couche `dolines` pour suivre chaque doline avant/après — cette
  colonne n'existe que sur les couches cibles P1/P2/P3 exportées, jamais sur
  `dolines` elle-même. Trouvé lors du premier test réel (modèle forcé sur
  Marnaval) : la comparaison restait vide sans aucune erreur ni
  avertissement. Corrigé en utilisant l'identifiant de ligne réel
  (`__fid__`) ; la logique de capture est désormais extraite dans
  `core/etude.py::capture_priorites()` (testée unitairement, y compris sur
  le schéma réel sans colonne `name`) plutôt que dupliquée en ligne dans
  l'algorithme.
- **Modèle « Jura plateau » ré-entraîné : la variable morte est retirée.**
  `jura_plateau_model.json` référençait encore `cold_air_index` (signalé en
  v1.5.1), une colonne qui n'est plus jamais calculée par le plugin —
  imputée à sa médiane pour chaque doline, un poids mort qui ne
  discriminait rien. Ré-entraîné sur 5 communes du plateau jurassien
  (Besain, Molain, Arc-sous-Cicon, Poligny, Chaux-Neuve) avec les
  features actuelles. AUC hors-échantillon (LOCO) : **0,633** (contre
  0,656 documenté avec l'ancienne variable, chiffres non directement
  comparables — l'ancienne colonne ne peut plus être recalculée pour
  refaire le test à l'identique). Deux communes candidates testées et
  écartées faute de signal (Saint-Maurice-Crillat 0,53 / La Châtelaine
  0,54, quasi hasard malgré un inventaire pur en gouffres) — confirme
  que la lithologie/densité ne suffit pas à distinguer plateau et vallée.
  Modèle toujours **opt-in**, jamais appliqué automatiquement.

## [1.5.1] — 2026-07-05

### Modifié
- **Documentation restructurée par public.** La section « Scoring des dolines »
  du README (validation AUC, anatomie du modèle appris, barème détaillé
  composante par composante, historique des révisions v2) faisait ~600 lignes
  d'un README de 1346 — dupliquée avec `docs/DOC_TECHNIQUE_DETECTION.md` et
  illisible pour un non-initié. Le README garde désormais l'essentiel opérationnel
  (comment utiliser l'outil, ce que veut dire chaque couleur/paramètre) ; le
  détail scientifique complet vit uniquement dans `DOC_TECHNIQUE_DETECTION.md`,
  **désormais fourni dans l'archive livrée** (annexe optionnelle, à côté du PDF)
  au lieu de rester dev-only.
- **Correctif** : un tableau markdown du README (contenu du GeoPackage) était
  coupé en deux par un encart inséré au milieu, cassant son rendu (deuxième
  moitié sans ligne d'en-tête). Réparé.
- Description du filtre canopée sur les gouffres dédupliquée (elle apparaissait
  deux fois, texte quasi identique).
- **`DOC_TECHNIQUE_DETECTION.md` revérifié contre le code actuel** (annexe
  désormais distribuée, donc engageante) : numéro de version ajouté en tête ;
  table des coefficients du modèle Barrois corrigée (valeurs obsolètes —
  `ratio_ps` notamment était donné à 0,627, la valeur réelle du modèle livré
  est 0,517 ; 8 variables et non 9) ; seuils de probabilité P1/P2/P3 corrigés
  en conséquence ; une piste testée manquante (ré-entraînement BaseKarst52,
  sans gain hors-domaine) ajoutée à la liste honnête des échecs.

### Note connue (non corrigée ici)
- `karstpro/models/jura_plateau_model.json` référence encore `cold_air_index`
  comme variable active (coefficient −0,167) alors que cette colonne n'est plus
  calculée nulle part dans le code : elle est donc imputée à sa médiane pour
  **chaque** doline, un poids mort qui ne discrimine rien (le modèle reste
  fonctionnel, juste sous-optimal). Nécessite un ré-entraînement du modèle
  Jura plateau, hors scope d'une revue de documentation.

## [1.5.0] — 2026-07-05

### Ajouté
- **Fichiers journaux rangés dans `logs/`.** Tous les `.log` générés par
  « Préparer une sortie », « Synchroniser », « Mettre à jour les cibles » et
  « Export MLL » vont désormais dans un sous-dossier `logs/` (à côté du
  `.gpkg`), au lieu d'être écrits directement dans le dossier d'étude ou dans
  `RapportSortie/`. Objectif : ne pas noyer les livrables (gpkg, CSV, PDF)
  parmi des fichiers de diagnostic. « Refaire une étude » (repli sans
  `karstpro_etude.json`) cherche le dernier log dans `logs/` **et** à la
  racine du dossier, pour ne pas casser les études préparées avant ce
  rangement.
- **Filtre canopée sur les gouffres** : les vides de NODATA en zone de
  végétation dense (bois, forêt, haie, verger…) ont la même signature qu'un
  puits — indiscernables géométriquement. Nouveau filtre BD Topo
  (`zone_de_vegetation`) : les candidats en canopée dense sont marqués
  **sans intérêt** (`interet = 0`) au lieu de « non visité », avec une
  nouvelle symbologie (gris atténué vs violet). Filtre PROBABILISTE : le
  candidat reste dans la couche, jamais supprimé, réversible en un clic sur
  le terrain. Vérifié sur Sommelonne : 88 % des 647 candidats détectés
  étaient en zone de végétation.
- **Fond SCAN25 (carte IGN classique 1/25 000), à clé personnelle** : paramètre
  avancé « Clé API SCAN25 personnelle » dans « Préparer une sortie ». SCAN25 est
  un produit **payant** de l'IGN (inscription SIRET sur cartes.gouv.fr —
  associations incluses, ex. club de spéléo ou FFS) : **KarstPro n'embarque
  aucune clé**, chaque utilisateur fournit la sienne. Laissé vide (cas par
  défaut), aucun effet — la préparation fonctionne normalement.

### Corrigé
- **« Préparer une sortie » pouvait perdre des verdicts terrain non
  synchronisés en cas de re-préparation.** Relancer la préparation sur un
  dossier déjà existant (« Retirer les cibles déjà prospectées » coché, cas
  par défaut) capturait tout `interet` non nul (0, 1 **ou** 2) vers l'archive
  « cibles visitées » — exactement le risque que « Refaire une étude »
  protège, mais **sans aucun garde-fou** sur cette voie. Une cavité ou un
  indice confirmé mais jamais exporté au CSV Karst Entry pouvait ainsi être
  piégé dans l'archive de façon définitive et invisible. Les 2 mêmes
  garde-fous que « Refaire une étude » (cavités non synchronisées, cibles/
  gouffres à intérêt non exportés) protègent désormais aussi la préparation.
- **Nom de secteur non échappé dans les requêtes SQL du report des cibles
  visitées.** Les noms de table étaient construits par concaténation directe
  du nom de secteur (texte libre, saisi ou géocodé) — un secteur contenant un
  guillemet double aurait produit du SQL invalide, voire injectable.
  Échappement systématique des identifiants ajouté.
- **Score morphologique faussé sur géométrie invalide.** Une doline dont
  `surface_m2`/`profondeur_m` valait `NaN` (géométrie dégénérée en amont)
  recevait le score **maximum** sur ces composantes (40 pts/129) au lieu du
  minimum, la poussant vers une priorité rouge/orange plutôt que de
  l'exclure.
- **Facteur karstifiabilité toujours à sa valeur par défaut avec une couche
  géologie locale.** `CODE_LEG` (index de légende BD Charm-50, propre à
  chaque feuille) était renommé en `NOTATION` lors du chargement d'une
  couche géologique locale, masquant le repli déjà prévu dans le calcul du
  score de contact géologique — le facteur karstifiabilité retombait alors
  toujours sur sa valeur par défaut (1.0) au lieu du facteur réel de la
  formation.
- **Robustesse du chargement du plugin** : garde-fous ajoutés contre un
  double enregistrement du fournisseur d'algorithmes (rechargement du
  plugin sans déchargement complet) et contre un déchargement avant
  initialisation.
- **Échappement XML manquant dans le générateur de projet `.qgs` hors QGIS**
  (utilisé en tests/CLI headless uniquement — le chemin normal, via l'API
  Qt, échappait déjà correctement) : un nom de secteur ou de couche
  contenant `&`, `<`, `>` ou `"` aurait produit un fichier projet corrompu.
- **Synchro retour terrain : les cibles à intérêt (indice/cavité) étaient
  supprimées sans archive.** `remove_cibles_by_interet` retirait de P1/P2/P3
  les cibles déjà exportées au CSV, mais sans jamais les déplacer dans
  « cibles visitées ». Or seule cette archive protège un emplacement d'une
  re-proposition à la préparation suivante (`suppress_already_visited`) : une
  cavité confirmée pouvait ainsi revenir se faire re-détecter comme cible
  neuve à l'infini. Remplacé par un archivage (`move_visited_to_archive` avec
  `only_interet={1, 2}`), comme pour les cibles sans intérêt.

## [1.4.0] — 2026-07-03

> Nouvel algorithme **« Refaire une étude »** : rejoue une préparation existante
> avec les mêmes paramètres (utile après un changement de traitement MNT/
> détection/scoring), avec ses garde-fous anti-perte de données et le report du
> verdict des gouffres à travers les re-préparations.

### Ajouté
- **« Refaire une étude »** (nouvel algorithme) : rejoue une préparation
  existante **avec les mêmes paramètres**, sans re-saisie. Relit
  `karstpro_etude.json` (écrit désormais à chaque préparation : paramètres +
  version + date), ou à défaut **parse le dernier log** pour les anciennes
  études (tri par horodatage du nom, robuste aux copies de dossier). Cases
  « Régénérer le MNT » / « Re-télécharger le LiDAR » pour invalider le cache
  `lidar_work/` selon ce qui a changé. Le retrait des cibles déjà
  prospectées/connues est **forcé**.
- **Garde-fous « Refaire une étude »** : bloque si des **cavités saisies non
  synchronisées** sont présentes (couche `cavites` non vide — la prép réécrirait
  le gpkg et les perdrait), ou si des **cibles/gouffres à intérêt** (indice/
  cavité, `interet ≥ 1`) ne sont pas encore synchronisés (sans cela, la
  re-préparation les piégeait dans l'archive « cibles visitées » sans jamais les
  envoyer au CSV Karst Entry — le carryover capture tout `interet != -1`
  indistinctement). Message explicite invitant à synchroniser d'abord, plutôt
  qu'une synchro automatique silencieuse (effets de bord : appels réseau,
  nouveaux rapports).
- **Report du verdict des gouffres à travers une re-préparation.** La couche
  `gouffres` est un signal physique (vide NODATA du MNT), régénérée entièrement
  à chaque prép, sans lien avec le terrain — un gouffre déjà investigué
  (`interet ≥ 1`) renaissait à `interet = -1` à chaque régénération. Le verdict
  (`interet`/`comment`/`photos`) est désormais **reporté** sur le gouffre
  fraîchement re-détecté à la même position (tolérance 3 m, appariement 1:1) —
  comme pour les cibles, mais sans archivage (les gouffres restent une
  référence permanente, jamais supprimés).
- **Synchro sans trouvaille : plus de dossier/CSV/PDF vides.** Si rien à
  exporter (aucune cavité saisie, aucune cible/gouffre à intérêt), la synchro
  ne crée plus `RapportSortie/JJ-MM-AAAA/` ni de CSV/PDF — seul un journal, à
  côté du `.gpkg` (comme « Mettre à jour les cibles »). L'extraction des labels
  terrain et le nettoyage des couches continuent de tourner (indépendants des
  « trouvailles » : un `interet = 0` alimente quand même l'apprentissage).
- **Traçabilité couche source → destination** dans les journaux de « Synchroniser
  le retour terrain » et « Mettre à jour les cibles » : pour chaque cible/gouffre/
  cavité déplacé ou exporté, une ligne précise `nom : « couche source » →
  « destination »` (archive « cibles visitées », ou « CSV Karst Entry »).

### Corrigé
- **« Refaire une étude » : dossier de sortie non cliquable** dans le panneau de
  résultats (affiché en texte brut, contrairement à « Préparer une sortie »).
  L'algorithme ne déclarait aucune sortie propre — ajout de `addOutput`
  (dossier), comme les autres algorithmes.
- **Libellés des cases à cocher raccourcis** (« Refaire une étude ») : les
  `QCheckBox` ne justifient pas le texte comme les `QLabel` des autres
  paramètres (même cause déjà rencontrée sur prép/sync).
- **Installeur de dépendances fiabilisé** (`install_deps.bat` / `.sh`) : vérifie
  désormais l'**import réel** des paquets par le Python de QGIS, au lieu de se
  fier au code retour de `pip` (qui renvoie 0 même quand il bascule en `--user`,
  invisible par QGIS si QGIS est dans `Program Files`). En cas d'échec sous
  Windows, **relance automatiquement en administrateur** (UAC) ; message clair
  (root / console Python QGIS) sinon. Évite le faux « installation réussie »
  suivi de `ModuleNotFoundError` au premier lancement.
- **Fenêtre whiteboxgeo.com au premier lancement** : la lib `whitebox` ouvrait la
  page de don dans le navigateur lors du téléchargement initial du binaire WBT.
  Neutralisé (`webbrowser.open` temporairement désactivé pendant l'init de
  WhiteboxTools, puis restauré).

## [1.3.0] — 2026-06-27

> Retour terrain réorienté vers **Karst Entry** : la synchro produit un CSV
> importable (au lieu d'écrire dans une couche inventaire), avec photos et
> altitude. KarstPro détecte et va sur le terrain ; Karst Entry gère l'inventaire.

### Ajouté
- **Export CSV Karst Entry au retour terrain** : la synchro produit
  `<secteur>_terrain_karstentry_<horodatage>.csv` (délimiteur « ; », WGS84,
  photos) importable directement dans Karst Entry. Rassemble **toutes les
  trouvailles** : cavités saisies + cibles à intérêt (`interet ≥ 1`) + gouffres
  visités à intérêt. Karst Entry dédoublonne à l'import.
- **Photo terrain** sur les couches `cavites`, `cibles` (P1/P2/P3) et `gouffres`
  (widget QField), intégrée au rapport PDF et au CSV.
- **Sélecteur de MNT dans la synchro retour terrain** : couche raster ou .tif,
  sous le GeoPackage. Sert au **calcul de l'altitude** des trouvailles. La plupart
  des projets QField n'embarquent pas le MNT (trop lourd pour le cloud) — on peut
  désormais le fournir au bureau. Sans MNT fourni, recherche auto à côté du gpkg.
- **Gouffres exportés réinitialisés** au nettoyage de la synchro : un gouffre
  visité à intérêt (`interet ≥ 1`), une fois son verdict exporté au CSV, repasse à
  « non visité » (la couche de référence reste, on ne supprime pas un gouffre
  connu) — évite la ré-export à la synchro suivante.
- **Journaux `.log`** pour « Synchroniser le retour terrain » et « Mettre à jour
  les cibles » (comme la préparation et l'export MLL) : tout le déroulé est
  recopié dans un fichier daté, même si la fenêtre Processing se ferme.
- **Couche `gouffres` éditable au formulaire QField** (`interet`/`comment`/
  `photos`, géométrie verrouillée) pour le **suivi de visite**.
- **Report des cibles déjà prospectées (couche « cibles visitées »)** : une
  re-préparation ne perd plus les verdicts terrain. Les cibles sans intérêt
  (`interet = 0`) sont conservées dans une archive séparée de la to-do P1/P2/P3,
  et les nouvelles cibles tombant au même endroit (≤ 5 m) sont retirées de la
  to-do. Case « Retirer les cibles déjà prospectées ou connues » (cochée par
  défaut).
- **Cibles connues retirées à la préparation** : si un inventaire est fourni, les
  cibles à ≤ 3 m d'une cavité connue (inventaire utilisateur + Géorisques) sont
  retirées de la to-do.

### Modifié
- **Synchro retour terrain : plus d'écriture directe dans une couche inventaire.**
  Le paramètre « couche inventaire » est supprimé ; on génère un CSV pour Karst
  Entry (qui dédoublonne à l'import). La synchro réutilise « Mettre à jour les
  cibles » pour le nettoyage et **vide la couche tampon `cavites`** ; case
  « Nettoyer les couches terrain » (cochée par défaut, destructive). Buffers GPS
  par défaut ramenés à 3 m (sync et MAJ cibles).
- **Paramètres avancés repliés par défaut** sur « Synchroniser le retour terrain »
  (distance de regroupement GPS, dossier du rapport) et « Mettre à jour les
  cibles » (couche source, buffer GPS) — comme la préparation et l'export MLL.
- **Couche géologie désormais complète** (BD Charm-50, *toutes* les formations)
  aux **couleurs officielles BRGM** ; le sous-ensemble karstifiable du score est
  dérivé à la volée. L'export MLL inclut une section « Contexte géologique ».

### Corrigé
- **Verdicts de cibles correctement aiguillés** au retour terrain : seules les
  cibles **sans intérêt** (`interet = 0`) vont dans « cibles visitées » ; celles à
  **intérêt** (`interet ≥ 1`) partent à l'inventaire (CSV) et sont retirées de
  P1/P2/P3 (avant, *toutes* les cibles visitées étaient archivées et aucune ne
  rejoignait l'inventaire).
- **Rapport PDF vide au retour terrain** : le PDF se construit désormais sur les
  trouvailles collectées **avant** le nettoyage des couches — il inclut cavités,
  cibles promues et gouffres (avec photos), au lieu d'être vide après nettoyage.

### Retiré
- **Indice de piégeage d'air froid (`cold_air_index`)** retiré de partout : calcul,
  schéma GPKG, scoring, export MLL/GPX, modèle Barrois (retrainé sans), doc. Une
  ablation LOCO sur le Barrois a montré que sa suppression **ne change pas l'AUC**
  (0,7159 vs 0,7158) — non-discriminant, redondant avec profondeur et P/√S.
- **Case « Inclure l'ombrage MNT dans le projet »** de la préparation : l'ombrage
  MNT est désormais toujours ajouté (retirer la couche avant le packaging cloud
  pour un paquet léger).

## [1.2.1] — 2026-06-26

### Ajouté
- **Fond ortho IGN (satellite)** dans le projet généré : couche WMS
  Géoplateforme `ORTHOIMAGERY.ORTHOPHOTOS` (20 cm, France entière), placée
  entre l'ombrage MNT et le Plan IGN. **Décochée par défaut** — l'utilisateur
  l'active à la demande ; une fois cochée, l'ombrage MNT (70 %) retombe dessus
  pour une vue « satellite + relief » de prospection. Source officielle IGN
  (même origine que le LiDAR), gratuite et légale — à l'inverse des tuiles
  Google XYZ. Exclue du packaging QField.
- **Coordonnées UTM WGS84 (mètres)** dans les exports CSV et le rapport PDF :
  en plus du Lambert-93 et du WGS84 décimal, chaque doline reçoit son easting /
  northing UTM et sa zone (`x_utm`, `y_utm`, `utm_zone`). Zone calculée
  automatiquement depuis la longitude (la France couvre les zones 30/31/32 N).
  Conversion en pur Python (Transverse Mercator de Snyder), sans `pyproj`
  (non thread-safe sous QGIS 4.0.2), validée à moins d'1 cm.
- **Filtre faux positifs anthropiques sur les dolines** (BD Topo carrières /
  zones d'activité) : une carrière est une vraie dépression mais pas un karst.
  Les dolines tombant sur une emprise anthropique sont **déclassées en gris**
  (colonne `flag_anthropique` conservée, score préservé, jamais supprimées),
  réactivable depuis la fenêtre de préparation. Réutilise le mécanisme déjà en
  place pour les gouffres.
- **Boucle d'apprentissage terrain** : champ `interet` sur les cibles
  (-1 non visité / 0 rien / 1 indice / 2 cavité), éditable au formulaire dans
  QField (géométrie verrouillée), et extraction automatique d'un CSV cumulatif
  `labels_terrain.csv` à la synchronisation — base pour le réentraînement des
  modèles de scoring.

### Performance
- **Détection des dolines** vectorisée : la profondeur et l'altitude par
  polygone passent d'une boucle `rasterize(MNT entier)` par doline à une seule
  passe `rasterize` étiquetée + `np.maximum.at`. Complexité O(n × H × W) →
  O(H × W) — gain proportionnel au nombre de dolines (×100 à ×1000 sur un grand
  secteur).
- **Détection des gouffres** : le remplissage par diffusion (BFS Python visitant
  chaque cellule NODATA, des millions en forêt) est remplacé par les composantes
  connexes vectorisées de `rasterio.features.shapes` (C). 11,8 s → 3,4 s sur
  Marnaval, résultat strictement identique.

### Corrigé
- **Symbologie des inventaires perdue** : les couches inventaire cavités /
  traçages référencées dans le projet récupèrent leur style embarqué via
  `loadDefaultStyle()` (style stocké dans la table `layer_styles` du GeoPackage
  par Karst Entry).

### Interne
- **Intégration continue** (GitHub Actions) : `pytest` sur push et pull request
  (Python 3.12). Découverte setuptools limitée à `karstpro*` (flat-layout) ;
  tests d'intégration WhiteboxTools désactivés en CI (binaire Linux instable).
- Config scoring JSON déplacée après les traçages dans la fenêtre de préparation.

## [1.2.0] — 2026-06-23

### Corrigé
- **Access violation au 2ᵉ lancement de la préparation** (depuis l'historique
  QGIS, même session) : `pyproj` (`proj_create`) n'est pas thread-safe dans le
  thread worker de Processing sur QGIS 4.0.2. Les deux créations explicites de
  CRS/Transformer du pipeline sont supprimées — `check_bdlisa_karst` convertit
  L93→WGS84 en pur Python (`_l93_to_wgs84`), et l'écriture du CRS du GeoPackage
  utilise des WKT EPSG:2154 codés en dur au lieu de `pyproj.CRS.from_epsg`.
- **Access violation au 2ᵉ lancement de « Mettre à jour les cibles »** (même
  cause pyproj). L'algorithme n'utilise plus `geopandas.read_file`/`to_crs`/
  `to_file` : lecture des couches GeoPackage en SQL pur (`read_gpkg_layer`,
  `crs=None`), couche source via l'API QGIS (`QgsCoordinateTransform`, thread-
  safe), écriture par suppression ciblée `DELETE` (`delete_features_by_fid`,
  préserve CRS et schéma).
- **Faux positifs gouffres en zone urbaine** : la requête WFS BD Topo plafonnait
  à **5000 bâtiments** (limite Géoplateforme), donc en bourg dense des milliers
  de bâtiments manquaient et les gouffres posés dessus échappaient au filtre. La
  requête est désormais **paginée** (`STARTINDEX`). Sur Marnaval : 5067 → 9608
  obstacles récupérés, 1031 → 2425 candidats écartés.
- **Création du paquet QField bloquée** (« conflicting sync actions » :
  des couches d'un même GeoPackage avaient des actions de synchronisation
  différentes). Toutes les couches partagent maintenant une action **uniforme**
  (`offline`) ; la consultation seule passe par le drapeau natif `readOnly`, pas
  par l'action. Seule la couche `cavites` reste éditable.

### Ajouté
- **Détection des gouffres / puits verticaux** (`core/shafts.py`, intégrée à
  l'étape 3 de la préparation, nouvelle couche `gouffres`). Un puits ouvert ne
  renvoie aucun point sol au LiDAR aéroporté → il apparaît dans le MNT comme un
  **trou de NODATA compact** (et **non** comme une cuvette), donc invisible à la
  détection de dolines. On le rattrape par sa signature de vide : amas de NODATA
  **compacts à bord de sol valide** (filtres taille / compacité / couronne).
  Validé sur le **Gouffre de la Peute Fosse** (Écot-la-Combe — puits de 4 m
  donnant sur une rivière souterraine), jusqu'ici raté. Élargit KarstPro du
  karst à dolines au **karst à gouffres**.
- **Filtre BD Topo (bâti / eau)** sur les candidats gouffres
  (`fetch_bdtopo_obstacles` + `flag_anthropic`, WFS Géoplateforme) : un vide de
  NODATA sur un **bâtiment** (le LiDAR voit le toit) ou un **plan d'eau** (le
  LiDAR ne revient pas de l'eau) n'est pas un gouffre — il est écarté
  automatiquement à l'étape 3. La Peute Fosse est conservée.
  - ⚠️ Limites assumées : la **canopée dense** (forêt) produit encore des faux
    positifs que BD Topo ne filtre pas. Les features **noyées** (inversac avec
    eau) et les gouffres **aménagés** (Padirac, coiffé de bâti) restent
    invisibles : dans ces cas le vide n'est pas dans le MNT — hors portée d'un
    détecteur morphologique.
- **Points d'eau karstiques référencés** (`fetch_points_eau`, WFS Géoplateforme,
  nouvelle couche `bdtopo_eau` à l'étape 3, étiquetée par toponyme et placée
  juste sous les gouffres / cavités Géorisques). Récupère les **sources, pertes,
  inversacs, résurgences et exutoires** déjà cartographiés en BD Topo
  (`noeud_hydrographique` Source/Perte/Exutoire + `detail_hydrographique` de
  nature karstique). ⚠️ C'est du **référencement, pas de la détection** (comme
  les cavités Géorisques) : on localise des features connues, on n'en découvre
  pas. Comble l'angle mort des gouffres **noyés** — l'inversac de Rachecourt
  (5 m de profondeur, raté par la morphologie car le LiDAR réfléchit sur l'eau)
  est présent en base comme nœud Source et ressort ainsi dans la préparation.
- **Champ `altitude` sur les cavités** (schéma v1.3.0, `cavites` et
  `cavites_connues`), **auto-renseigné depuis le MNT IGN 1 m** au retour terrain
  (`fill_altitude_from_mnt`) — le MNT n'étant pas embarqué sur le téléphone, le
  remplissage se fait à la synchronisation, sans écraser une altitude saisie à
  la main. Affiché dans la fiche PDF.
- **Export MLL enrichi des gouffres et des points d'eau** : le prompt inclut
  désormais les gouffres détectés proches d'une cible (renfort d'hypothèse
  « puits vertical ») et les points d'eau `bdtopo_eau` référencés, chacun avec
  la **distance à la cible la plus proche**.
- **Export MLL — filtre spatial de l'inventaire sur la box d'étude** :
  l'inventaire peut couvrir un département entier ; seules les cavités connues
  (et traçages) **dans l'emprise analysée** sont injectées. Robuste au CRS de
  l'inventaire (conversion de la box si l'inventaire est en WGS84).
- **Export MLL — JSON borné** : le dump brut ne contient plus que P1+P2+P3
  (plafond 300 meilleures P2/P3), au lieu de toutes les dolines — les grises
  hors-seuil faisaient exploser la fenêtre de contexte du LLM. Nettoyage des
  champs texte (`clean_text`) avant injection (retire le boilerplate Office
  collé dans un commentaire d'inventaire).

## [1.1.0] — 2026-06-14

Version majeure : KarstPro passe d'un score morphologique manuel à une
**priorisation par modèle appris, validé hors-échantillon, par domaine
géologique**.

### Ajouté
- **Modèle appris par domaine** (régression logistique, inférence numpy pure —
  aucune dépendance ajoutée). Pilote les priorités P1/P2/P3 via une probabilité
  calibrée (colonne `score_ml`) là où il est validé.
  - **Barrois** (Meuse / Haute-Marne, karst sous couverture) — appliqué
    **automatiquement**. AUC hors-échantillon **0,65–0,72** contre ~0,57 pour
    les poids manuels.
  - **Jura plateau** (Doubs / Jura, karst nu à gouffres) — modèle **opt-in**,
    AUC **0,66** (validation croisée 4 communes). Activé explicitement par
    l'utilisateur.
- **Routeur multi-modèles** : sélection automatique selon le domaine (lithologie
  NOTATION BD Charm-50 + distance géographique + veto dur à distance). Registre
  par simple dépôt de `models/*.json`. Les modèles **opt-in** sont *suggérés*,
  jamais appliqués en silence.
- **Menu « Priorisation »** : *Automatique* (défaut) / *Poids manuels* / *Forcer
  un modèle opt-in* (ex. Jura plateau, sur jugement géologique).
- **TPI 500 m terrain réel** (moyenne focale du MNT, image intégrale) au lieu du
  proxy « dolines voisines ».
- **Outils de validation** : harnais hors-échantillon contre inventaire spéléo
  indépendant + outils de campagne terrain (échantillon aveugle stratifié,
  analyse Wilson/Fisher).
- **Documentation** : section « Modèles par domaine » + **carte des zones
  d'application** ; lexique (AUC, hors-échantillon…) ; présentation et discours
  à jour. Paquet avec README vitrine + logo et installation des dépendances
  embarquée.

### Modifié / amélioré
- **Robustesse mémoire** : les analyses de grande emprise (150+ dalles) ne
  saturent plus la RAM et n'abandonnent plus silencieusement les attributs cold
  air / pente / TPI (scores complets garantis). Résultats inchangés (lecture du
  MNT par fenêtre + bandes, float32, image intégrale int32).
- **Performances scoring** : mémoïsation géologie (bord de polygone, facteur de
  karstifiabilité) — auparavant recalculés pour chaque doline.
- **Export MLL** : prompt restructuré et durci (coordonnées WGS84 précalculées,
  pas de recalcul délégué au LLM, biais d'exploration documenté).
- **Audit de code** : suppression de code mort, docstrings, corrections diverses.

### Corrigé
- **Facteur de karstifiabilité par NOTATION** (et non CODE_LEG, index de légende
  instable d'une feuille à l'autre) : le facteur ne s'appliquait quasiment jamais.
- Corrections factuelles de la documentation et de la présentation (MNT **1 m**,
  classe LAS **2** seule, seuils de détection > 0,1 m / ≥ 10 m², limite physique
  ~18 %, stack PDAL/whitebox…).

### Notes — limites assumées (honnêteté scientifique)
- L'AUC **plafonne à ~0,65 par domaine** : limite *physique* de la morphologie de
  surface (la forme d'une doline prédit faiblement le vide souterrain). Failles
  BRGM, linéaments LiDAR, développement des cavités et hydrologie (thalwegs secs)
  ont été testés **sans gain** et sont documentés comme négatifs.
- La détection **automatique** du sous-régime (plateau vs vallée/reculée, de même
  lithologie) est **impossible** depuis le MNT (*concept drift* indétectable sans
  cavités déjà connues) → d'où les modèles **opt-in**.

## [1.0.0]

Première version publique.
- Pipeline LiDAR HD IGN → MNT 1 m (TIN) → remplissage des dépressions (Wang &
  Liu 2006) → détection de dolines → **scoring morphologique manuel** (Bloc A,
  poids configurables) → priorités P1/P2/P3.
- Export GeoPackage + projet QField + GPX + prompt MLL.
- Workflow bureau ↔ terrain (QField), synchronisation du retour terrain et
  promotion vers l'inventaire des cavités.
