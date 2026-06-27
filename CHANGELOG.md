# Changelog — KarstPro

Évolutions notables du plugin. Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/),
versionnage sémantique. Les paquets distribués sont nommés `KarstPro_v<version>_<date>.zip`.

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
