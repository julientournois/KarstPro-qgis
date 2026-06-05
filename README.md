<p align="center">
  <img src="logo.png" alt="KarstPro" width="320">
</p>

# KarstPro — Documentation

> Prospection karstique assistée par QGIS et QField — analyse LiDAR HD IGN,
> détection de dolines, scoring morphométrique, workflow terrain.

## Prérequis

- QGIS ≥ 3.34 LTR (testé sur QGIS 3.40 et QGIS 4.0.2)
- PDAL est **inclus** avec QGIS — pas besoin de l'installer séparément
- Connexion internet pour le premier lancement (téléchargement LiDAR IGN + BRGM)

---

## Installation — Windows

### Dépendances Python

Double-cliquer sur **`install_deps.bat`** (à la racine du repo) — le script détecte
automatiquement QGIS 3 ou 4 dans `C:\Program Files` et `D:\Program Files` et installe
les dépendances dans le Python bundlé avec QGIS.

> ⚠️ Si Windows demande une confirmation UAC ou si l'installation échoue,
> relancer en **clic droit → Exécuter en tant qu'administrateur**.

En cas d'installation QGIS dans un dossier non standard, éditer la ligne en haut
du script :
```bat
set PYTHON_EXE=C:\chemin\vers\QGIS\apps\Python312\python.exe
```

### Déploiement du plugin (après chaque modification des sources)

**QGIS 4.0.2 :**
```powershell
Copy-Item -Path ".\karstpro\*" `
  -Destination "$env:APPDATA\QGIS\QGIS4\profiles\default\python\plugins\karstpro\" `
  -Recurse -Force
```

**QGIS 3.40 :**
```powershell
Copy-Item -Path ".\karstpro\*" `
  -Destination "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\karstpro\" `
  -Recurse -Force
```

Ou utiliser `deploy_plugin.bat` à la racine du repo — détecte automatiquement QGIS 4.x ou 3.x.

---

## Installation — Linux

Testé sur Ubuntu 22.04 / 24.04 et Debian 12. Les commandes sont identiques sur
les distributions basées sur apt (Mint, Pop!_OS…).

### 1. Installer QGIS

```bash
# Ajouter le dépôt officiel QGIS (clé + sources)
sudo mkdir -p /etc/apt/keyrings
sudo wget -O /etc/apt/keyrings/qgis-archive-keyring.gpg \
    https://download.qgis.org/downloads/qgis-archive-keyring.gpg

# Ubuntu 24.04 (noble) — adapter "noble" à ta version
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/qgis-archive-keyring.gpg] \
    https://qgis.org/ubuntu noble main" \
    | sudo tee /etc/apt/sources.list.d/qgis.list

sudo apt update
sudo apt install qgis qgis-plugin-grass python3-qgis
```

> Pour Debian ou d'autres versions Ubuntu, adapter le nom de la distribution dans
> la ligne `deb` (`bookworm`, `jammy`…). Guide complet :
> [download.qgis.org](https://qgis.org/resources/installation-guide/).

### 2. Dépendances Python

Rendre le script exécutable puis le lancer depuis la racine du repo :

```bash
chmod +x install_deps.sh
./install_deps.sh
```

Le script détecte automatiquement QGIS (apt, conda/mamba, venv) et choisit
les bonnes options pip (`--user`, installation système ou venv).

Cas particuliers gérés automatiquement :
- **apt** (`python3-qgis`) → `pip install --user`
- **conda/mamba** (env actif) → `pip install` sans `--user`
- **root** → installation système
- **Flatpak** → instructions spécifiques affichées, pas d'installation automatique

### 3. Déploiement du plugin

Le dossier plugins QGIS est `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
(identique pour QGIS 3.x et 4.x sur Linux) :

```bash
PLUGIN_DIR="$HOME/.local/share/QGIS/QGIS3/profiles/default/python/plugins/karstpro"
mkdir -p "$PLUGIN_DIR"
cp -r karstpro/* "$PLUGIN_DIR/"
```

Pour un déploiement rapide après modification des sources :

```bash
# Depuis la racine du repo
rsync -av --delete karstpro/ \
    ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/karstpro/
```

> ⚠️ QGIS 4.x sur Linux peut utiliser un chemin différent selon la version
> (`QGIS4` au lieu de `QGIS3`). Vérifier avec :
> ```bash
> python3 -c "from qgis.core import QgsApplication; \
>     print(QgsApplication.qgisSettingsDirPath())"
> ```

### 4. Activer le plugin dans QGIS

Même procédure que Windows :

1. Lancer QGIS
2. Menu **Extensions → Gérer et installer des extensions → Installées** → activer **KarstPro**
3. Les algorithmes apparaissent dans : **Traitement → Boîte à outils → KarstPro**

### Notes spécifiques Linux

| Sujet | Détail |
|-------|--------|
| **PDAL** | Inclus avec QGIS (paquet `qgis`). Si absent : `sudo apt install pdal python3-pdal` |
| **whitebox** | Le package pip `whitebox` télécharge un exécutable Go au premier lancement — connexion internet requise. Peut échouer derrière un proxy d'entreprise. Alternative : `whitebox-tools` binaire précompilé depuis [github.com/jblindsay/whitebox-tools](https://github.com/jblindsay/whitebox-tools) |
| **GDAL / fiona** | Généralement fournis avec QGIS. Si erreur `fiona` au lancement : `pip3 install fiona --no-binary fiona` |
| **Permissions** | `pip3 install --user` installe dans `~/.local/lib/` — pas besoin de sudo et visible par QGIS |
| **Firewall / proxy** | Les téléchargements IGN LiDAR nécessitent l'accès à `data.geopf.fr` (HTTPS). Configurer `http_proxy` / `https_proxy` si besoin |

---

## Structure attendue dans le dossier plugins

```
plugins/
  karstpro/
    __init__.py
    metadata.txt
    karstpro_plugin.py
    karstpro_provider.py
    algorithms/
    core/
    config/
```

> ⚠️ `metadata.txt` doit être **à l'intérieur** du dossier `karstpro/`, pas à la racine du repo.

---

## Données utilisées (automatiques, aucune config requise)

| Source | Service | Remarque |
|--------|---------|----------|
| IGN LiDAR HD | `data.geopf.fr` (WFS + téléchargement COPC) | ~160–200 MB par dalle km², résolution 1 m |
| BRGM lithologie | `geoservices.brgm.fr/geologie` | WFS GML 3.2, layer `ms:LITHO_1M_SIMPLIFIEE` — utilisé si aucune géologie locale fournie |
| BD Charm-50 (auto) | Cache `karstpro/data/geo50k/` (dans le plugin) | Carte géologique 1/50 000 BRGM. KarstPro détecte automatiquement les départements intersectant la bbox, télécharge les données manquantes depuis Infoterre et les met en cache **dans le dossier du plugin** (`…/plugins/karstpro/data/geo50k/`). Un cache existant à la racine du dépôt (dev) ou sous `~/karstpro_data/geo50k` est réutilisé en priorité s'il est présent. Fallback automatique sur le WFS 1/1 000 000 si la zone est hors cache. |
| BDLISA zones karstiques | `reseau.eaufrance.fr` (WFS) | Vérification pré-traitement uniquement — non bloquant si indisponible |
| Géorisques — cavités souterraines | `georisques.gouv.fr` (WFS) | Layer `CAVITE_LOCALISEE` — points, lecture seule dans QField |

---

# Guide d'utilisation

## Guide pas à pas illustré — du bureau au terrain

Ce parcours suit **un cycle de sortie complet**, étape par étape, avec captures.
En résumé :

1. **Préparer** un secteur au bureau (LiDAR → dolines scorées → projet QGIS).
2. **Envoyer** le projet sur le téléphone via QFieldCloud.
3. **Saisir** les cavités sur le terrain dans l'app QField.
4. **Rapatrier** les saisies au bureau (QFieldSync).
5. **Mettre à jour l'inventaire** des cavités connues + générer le rapport.
6. *(optionnel)* **Recalculer les cibles** puis **exporter pour l'analyse MLL**.

La section *Pré-sortie* qui suit détaille ensuite chaque paramètre.

### Trouver les outils KarstPro

Ouvrir la **boîte à outils Traitement** (menu *Traitement → Boîte à outils*, ou
l'icône engrenage dans la barre d'outils) :

![Icône de la boîte à outils Traitement dans QGIS](docs/img/QGISBoiteAOutils.png)

KarstPro apparaît comme un groupe contenant **4 outils** :

![Le groupe KarstPro et ses 4 outils](docs/img/BoiteAOutils.png)

### Étape 1 — Préparer une sortie (bureau)

Double-cliquer sur **KarstPro — Préparer une sortie**. Dessiner la **zone
d'étude** sur la carte. Le **nom du secteur** peut être laissé vide : il sera
rempli automatiquement avec la commune au centre de la zone. Tout le reste est
dans **Paramètres avancés** (replié, optionnel) — dont les GeoPackages
inventaire/traçages et l'ombrage MNT :

![Fenêtre « Préparer une sortie », section avancée dépliée](docs/img/FenetrePreparerSortie.png)

Cliquer sur **Exécuter** : KarstPro télécharge le LiDAR, génère le MNT, détecte
les dolines, calcule le score et prépare le projet QGIS (5–20 min selon la
surface). Le **dossier de sortie** contient le projet `.qgs`, le GeoPackage
`.gpkg` (dolines, cibles, géologie…), le dossier de travail `lidar_work/` (MNT,
LAZ — réutilisés aux relances) et le journal `.log` :

![Contenu du dossier de sortie après préparation](docs/img/ContenuDossiersEtSousDossiersProjets.png)

> 💡 **Convention : une étude = un dossier.** Chaque secteur a son propre dossier
> de sortie (projet, GeoPackage, rapports), donc aucun risque que les fichiers de
> deux études se télescopent.

### Étape 2 — Ouvrir le projet et vérifier (bureau)

> ⚠️ **Ouvrir le `.qgs`, pas le `.gpkg`** — seul le projet `.qgs` contient la
> mise en page complète (relief, fond de carte, styles).

La carte se cadre sur les cibles P1. Le panneau **Couches** liste tout ce que
KarstPro a préparé : dolines, cibles P1/P2/P3, hydrologie, géologie, courbes de
niveau, MNT en ombrage, fond Plan IGN — et, en lecture seule, l'**Inventaire
Cavités** et l'**Inventaire Traçages** référencés (non copiés) :

![Projet QGIS : couches préparées et carte des cibles](docs/img/QGSProjetCOucheCarte.png)

### Étape 3 — Envoyer le projet sur le téléphone (QFieldCloud)

Avec le projet ouvert, ouvrir **QFieldSync → Projets QFieldCloud**, puis créer un
nouveau projet. Choisir **« Convertir le projet actuellement ouvert en projet
cloud »** :

![QFieldSync — convertir le projet ouvert en projet cloud](docs/img/ImportQfield2.png)

Renseigner le **nom** et le **répertoire local** du projet, puis **Créer** :

![QFieldSync — détails du projet cloud](docs/img/ImportQfield3.png)

QFieldSync convertit les couches en GeoPackage et téléverse le projet. Une fois
terminé, il apparaît dans la liste QFieldCloud :

![Le projet est créé sur QFieldCloud](docs/img/ImportQfield5.png)

Le projet est maintenant disponible pour le téléphone (étape 4).

> 💡 **Alléger le paquet cloud.** Le MNT en ombrage est un raster volumineux que
> QFieldCloud copie tel quel sur le téléphone (le flag d'exclusion par couche
> n'est pas honoré côté cloud). Deux options : décocher *« Inclure l'ombrage
> MNT »* dès l'étape 1 (le relief n'apparaît alors ni au bureau ni au terrain),
> ou **retirer la couche MNT du projet juste avant la conversion QField** puis la
> ré-ajouter ensuite au bureau si tu en as besoin.

### Étape 4 — Sur le téléphone : télécharger et saisir (QField)

Sur le téléphone, ouvrir **QField** et appuyer sur **Projets QFieldCloud** (se
connecter au même compte) :

![Écran d'accueil de QField](docs/img/Accueil.jpg)

Le projet préparé apparaît comme **disponible sur le cloud** — appuyer dessus
pour le télécharger :

![Le projet est disponible sur QFieldCloud](docs/img/ProjetCloudDisponnible.jpg)

Une fois ouvert, la carte affiche les dolines scorées, les cibles et le fond de
plan. Pour saisir une cavité découverte, se placer dessus : le **viseur central**
suit la **position GPS**. Appuyer sur **« + »** pour créer le point à cette
position :

![Saisie d'une cavité à la position GPS (viseur central)](docs/img/CreationDepuisLocalisation.jpg)

La **fiche de saisie** de la couche `cavites` s'ouvre : renseigner nom, type,
dimensions, développement, explorateurs, photos… puis valider (✓). Les couches
inventaire et cibles restent en lecture seule.

![Fiche de saisie d'une cavité dans QField](docs/img/SaisieCavite1.jpg)

> 💡 La position est obligatoire : si le GPS n'a pas de fix, l'enregistrement est
> bloqué — pas de cavité « fantôme » sans coordonnées.

En fin de sortie (ou dès qu'il y a du réseau), **pousser les modifications** vers
QFieldCloud depuis l'écran de synchronisation de QField :

![Synchroniser les saisies vers QFieldCloud](docs/img/PushModificationToCLoud.jpg)

### Étape 5 — Rapatrier les saisies au bureau

De retour au bureau, ouvrir le projet et lancer **QFieldSync → Synchroniser**.
QField télécharge le GeoPackage modifié depuis le cloud (action *Download*) :

![QFieldSync — rapatrier le GeoPackage du cloud](docs/img/SyncCaviteQfieldCloudToLocal.png)

Les cavités saisies sur le terrain apparaissent alors dans la couche `cavites`
du projet QGIS (ici « Gouffre 12 » et « Perte marquis ») :

![Les cavités terrain rapatriées dans QGIS](docs/img/QGSProjetCarteNewCavite.png)

### Étape 6 — Mettre à jour l'inventaire + rapport

Lancer **KarstPro — Synchroniser le retour terrain**. Deux champs suffisent : le
**GeoPackage du projet QField** rapatrié, et la **couche inventaire « Inventaire
Cavités »** à mettre à jour :

![Fenêtre « Synchroniser le retour terrain »](docs/img/FenetreRetourTerrain.png)

Pour chaque nouvelle cavité, l'outil génère une **référence** automatique, résout
la **commune** (géocodage), et ignore les cavités déjà présentes. Un **rapport
PDF** de la sortie est produit — une fiche par cavité avec tous les champs et les
coordonnées L93/WGS84 :

![Rapport de sortie : une fiche par cavité](docs/img/RapportFicheCavite.png)

Pour partager l'inventaire enrichi avec le terrain, re-synchroniser le projet
vers QFieldCloud (QFieldSync envoie l'inventaire et le rapport mis à jour) :

![QFieldSync — renvoyer l'inventaire mis à jour vers le cloud](docs/img/SyncCaviteQfieldCloudToCloud.png)

### Étape 7 — (optionnel) Recalculer les cibles

Après plusieurs sorties, **KarstPro — Mettre à jour les cibles** réévalue les
priorités en tenant compte des cavités nouvellement connues :

![Fenêtre « Mettre à jour les cibles »](docs/img/FenetreMAJCibles.png)

### Étape 8 — Exporter pour analyse MLL

Pour obtenir une analyse priorisée et un ordre de visite, lancer **KarstPro —
Exporter pour analyse MLL**. Seul le **GeoPackage** est requis (le dossier de
sortie vaut par défaut celui du GeoPackage) ; inventaire, traçages et contexte
sont en options avancées :

![Fenêtre « Exporter pour analyse MLL »](docs/img/FenetreExportAnalyse.png)

L'export produit un prompt `mll_prompt_*.txt` (rapport complet inclus), les
waypoints `cibles_*.gpx` (cibles rouges et oranges) et un journal `.log`.

---

## Pré-sortie (bureau QGIS)

### 1. Préparer une sortie

**Traitement → Boîte à outils → KarstPro → Préparer une sortie**

**Paramètres requis** (toujours visibles) :

| Paramètre | Description |
|-----------|-------------|
| Nom du secteur | Nom court (ex. `Bayard sur marne`) |
| Zone d'étude (bbox) | Dessiner sur la carte — rester sous ~4 km² pour la première utilisation |
| Dossier de sortie | Dossier local où seront créés le GeoPackage et les fichiers de travail |

**Paramètres optionnels** — regroupés dans la section **« Paramètres avancés »**,
repliée par défaut (cliquer pour la déplier) :

| Paramètre | Description |
|-----------|-------------|
| Topo réseau existant | Fichier `.shp` ou `.kml` exporté depuis Visual Topo |
| Config scoring JSON | Laisser vide pour utiliser `config/default_scoring.json` |
| Cavités connues | Couche QGIS des cavités déjà répertoriées dans le secteur |
| Traçages hydrologiques | Couche lignes (`Inventaire Traçages` de Karst Entry, pré-sélectionnée si présente). Copiée dans le gpkg sous la couche `tracages` ; l'export MLL la relit automatiquement pour enrichir l'interprétation. |
| MNT pré-téléchargé(s) | Dernier recours si le CDN IGN est trop lent : charger directement les dalles `LHD_FXX_…_MNT_….tif` déjà téléchargées manuellement. Une seule dalle est copiée telle quelle ; plusieurs dalles sont fusionnées automatiquement par mosaïque (rasterio.merge). Le pipeline LAZ est alors ignoré. |
| Géologie locale BD Charm-50 1/50 000 | Forcer un GPKG ou shapefile spécifique (priorité absolue sur le cache auto). Utile pour tester une version modifiée ou une zone hors cache. |
| Courbes de niveau — équidistance (m) | Génère une couche `courbes_niveau` dans le GPKG. Défaut **5 m** ; **0 = désactivé**. Les courbes maîtresses (multiples de 10 m) sont tracées en gras et portent leur cote `NNN m`. |

**Durée estimée :** 5–20 min selon la surface (téléchargement LiDAR inclus).
Les dalles LiDAR déjà téléchargées sont réutilisées automatiquement lors des relances.
Le téléchargement est parallélisé sur 3 threads avec reprise automatique (15 tentatives,
backoff exponentiel) en cas d'erreur réseau ou HTTP 5xx.

> **Fichier journal persistant :** Un fichier `karstpro_prep_<secteur>_<horodatage>.log`
> est créé dans le dossier de sortie au démarrage de l'algorithme. Il reçoit en temps réel
> toutes les étapes et avertissements — utile pour diagnostiquer un problème si la fenêtre
> QGIS se ferme ou si les messages de traitement sont perdus.

> **Données externes récupérées automatiquement à chaque lancement :**
> - **BDLISA** — vérifie que la zone est en contexte karstique avant tout traitement.
>   Un warning s'affiche si aucune entité karstique n'est détectée ; le traitement
>   continue dans tous les cas. Ignoré silencieusement si le service est indisponible.
> - **BRGM lithologie** — polygones lithologiques pour le scoring (contact géologique).
> - **Géorisques BRGM** — cavités souterraines inventoriées dans la bbox (`CAVITE_LOCALISEE` :
>   nom, type, identifiant BRGM). Ajoutées au GPKG en couche `cavites_georisques`, lecture
>   seule dans QField. Un résultat vide est normal dans les karsts sous couverture peu
>   inventoriés — la base Géorisques est exhaustive dans les grands massifs calcaires
>   (Dordogne, Jura, Ardèche) mais lacunaire en Champagne-Ardenne.

**Résultat :** Un fichier `<secteur>.gpkg` et un fichier `<secteur>.qgs` dans le dossier
de sortie. Le GeoPackage contient :

| Couche | Type | Rôle |
|--------|------|------|
| `dolines` | Polygone | Dépressions détectées, scorées par priorité (rouge/orange/jaune/gris) |
| `<secteur> — cibles P1` | Point | Centroïdes des dolines rouges (score ≥ 55) — créé automatiquement à la fin de la préparation |
| `<secteur> — cibles P2` | Point | Centroïdes des dolines oranges (score 35–54) — créé automatiquement à la fin de la préparation |
| `<secteur> — cibles P3` | Point | Centroïdes des dolines jaunes (score 25–44) — masqué par défaut, à activer si besoin |

> **Identifiant des dolines** : chaque cible porte un `name` `doline_N`,
> où `N` est le **`fid` (1-based) de la couche `dolines`**. Ce même `N` est repris
> dans le rapport et le GPX de l'export MLL — identifiant unique et cohérent entre
> la carte, la table attributaire et le rapport.
| `hydrologie` | Ligne | Réseau D8 |
| `geologie` | Polygone | Lithologie BRGM |
| `topo_reseau` | Ligne | Réseau spéléo connu (si fourni) |
| `courbes_niveau` | Ligne | Courbes de niveau du MNT (si activées). Champs `ELEV` (cote m) et `maitresse` (1 = multiple de 10 m, tracée en gras + étiquetée). |
| `cavites_connues` | Point | Cavités déjà répertoriées (couche optionnelle fournie par l'utilisateur) — lecture seule |
| `cavites_georisques` | Point | Cavités BRGM Géorisques dans la bbox — utilisées dans le calcul de proximité `cavite_connue_proche`, lecture seule dans QField (absent si zone non inventoriée) |
| `cavites` | Point | Saisie terrain — **éditable dans QField** (seule couche éditable) |

**Attributs de la couche `dolines` :**

| Colonne | Type | Description |
|---------|------|-------------|
| `surface_m2` | float | Superficie de la dépression (m²) |
| `profondeur_m` | float | Profondeur max mesurée (MNT rempli − MNT original) |
| `altitude_m` | float | Altitude du centroïde (MNT IGN 1 m) |
| `ratio_ps` | float | P/√S — indicateur de verticalité (potentiel gouffre) |
| `pente_max_bord` | float | Pente max sur l'anneau périphérique (°) — signal d'effondrement |
| `lisere` | bool | Appartient à un alignement directionnel de dolines (karst de contact) |
| `cold_air_index` | float | Indice de piégeage d'air froid [0–1], calculé depuis le MNT 1 m |
| `score_morpho` | float | Score morphologique (= score final) |
| `score` | float | Score sur 100 |
| `priorite` | str | `rouge` / `orange` / `jaune` / `gris` |
| `bassin_versant_m2` | float | Surface du bassin versant amont drainant vers la doline (m²), depuis le flow acc D8 |
| `type_doline` | str | Classification automatique : `doline` / `doline-perte` / `perte` |
| `comp_absorption` | bool | ✓ = bassin versant ≥ 5 000 m² (captage significatif) |
| `comp_geologie` | bool | ✓ = centroïde sur formation karstifiable BD Charm-50 (25 pts garantis) |
| `comp_dist_reseau_m` | float | Distance au passage topo le plus proche (m) — informatif, hors score |
| `comp_in_couloir` | bool | ✓ = dans le couloir de galeries (buffer 500 m autour du réseau topo) — informatif, hors score |
| `comp_densite_500m` | int | Nombre de dolines voisines dans un rayon de 500 m |

### 2. Configuration QField (automatique)

Le fichier `.qgs` généré intègre la configuration QFieldSync :

- **`cavites`** : éditable hors ligne, géométrie capturée automatiquement
  par le GPS lors de la création d'un point (pas besoin de tapper sur la carte)
- **`dolines`, `hydrologie`, `geologie`, `topo_reseau`** : en lecture seule dans QField

### 3. Transférer sur le téléphone

**Option A — QFieldCloud (recommandé)**
1. Dans QGIS, ouvrir le plugin **QFieldSync** (icône dans la barre d'outils ou menu Extensions)
2. Configurer ton compte QFieldCloud si ce n'est pas déjà fait
3. **Packager le projet** puis **Synchroniser vers QFieldCloud**
4. Sur le téléphone : ouvrir QField → synchroniser le projet

**Option B — Fichier direct**
- Copier le `.gpkg` et le `.qgs` dans un dossier accessible par QField sur le téléphone
- Dans QField : ouvrir le `.qgs`

---

## Terrain (QField)

1. Ouvrir le projet `.qgs` dans QField
2. La carte affiche les dolines scorées (rouge/orange/jaune/gris) et les cibles P1/P2/P3
3. Pour chaque phénomène visité :
   - Appuyer sur **"+"** dans la couche `cavites`
   - Le formulaire s'ouvre et le point est placé **automatiquement à ta position GPS**
4. Types de cavités disponibles : `gouffre`, `grotte`, `résurgence`, `perte`, `inversac`
5. Re-synchroniser via QFieldCloud dès que le réseau est disponible

---

## Post-sortie (bureau QGIS)

### Synchroniser le retour terrain

**Traitement → Boîte à outils → KarstPro → Synchroniser le retour terrain**

| Paramètre | Description |
|-----------|-------------|
| GeoPackage QField | Le `.gpkg` retourné par QField (ou téléchargé depuis QFieldCloud) |
| GeoPackage principal | **Optionnel** — base cumulative. Laisse vide si l'inventaire est ta seule base et que tu promeus directement (workflow à deux gpkg) |
| Dossier rapport | Où générer le rapport PDF |
| Seuil dédoublonnage GPS | Distance en mètres sous laquelle deux points sont fusionnés (défaut : 10 m) |
| Promouvoir vers l'inventaire | Si coché, transfère les cavités terrain validées vers l'inventaire (`Inventaire Cavités`) puis **vide la couche tampon `cavites`** |
| Couche inventaire chargée | La couche `Inventaire Cavités` de destination, **chargée dans le projet** (rafraîchissement direct à l'écran après transfert) |
| GeoPackage inventaire cible | Alternative si la couche n'est pas chargée : pointe un `.gpkg` sur disque. **Peut être le gpkg principal** → la promotion vise la couche `cavites_connues` (créée si absente), jamais `cavites`. Seul le gpkg QField est refusé |

**Résultat :**
- Le GeoPackage principal est mis à jour avec les nouvelles cavités
- Une sauvegarde `.bak.gpkg` est créée automatiquement
- Un rapport PDF `rapport_<secteur>_<date>.pdf` est généré

**Promotion (zone tampon → inventaire) :** la couche `cavites` est un **sas** de
capture terrain, pas un catalogue. Une fois les cavités validées au bureau,
coche *Promouvoir vers l'inventaire* : les points non déjà présents (clé
`reference` sinon proximité GPS) sont ajoutés à `Inventaire Cavités`, les
métriques terrain (développement estimé, dimensions d'entrée) sont repliées dans
le `comment`, la **localisation administrative** (commune / code INSEE / code
postal / département) est résolue par géocodage inverse sur `geo.api.gouv.fr`
— comme à la saisie dans Karst Entry — et la couche tampon `cavites` est vidée.
Le géocodage met en cache les contours communaux : **un seul appel réseau par
commune** pour tout le lot (les cavités groupées d'une sortie partagent la
requête). Au cycle de prospection
suivant, l'inventaire alimente `cavites_connues` (flag `cavite_connue_proche`) :
tu ne re-prospectes pas ce qui est déjà connu. La promotion est **tout-ou-rien**
sur le contenu courant du tampon — ne la coche que lorsque tu as validé le lot.

**Deux façons de désigner l'inventaire cible** (fournis-en une seule ; la couche
chargée a priorité si les deux sont renseignées) :
- **Couche chargée** — sélectionne `Inventaire Cavités` dans le déroulant après
  l'avoir ajoutée au projet. La couche se rafraîchit immédiatement à l'écran.
- **GeoPackage sur disque** — pointe le fichier `.gpkg` de l'inventaire si tu ne
  veux pas le charger. L'algo détecte la couche (table portant le noyau
  `name`/`reference`, par défaut `Inventaire Cavités`, le tampon `cavites` est
  exclu) et **refuse** seulement le gpkg QField (retour terrain brut).

**Workflow recommandé (cloud, inventaire séparé)** — deux gpkg, le plus robuste :
1. L'opérateur maintient un **gpkg inventaire séparé** (`Inventaire Cavités` +
   traçages) via Karst Entry. C'est le système de référence.
2. *Préparer une sortie* consomme cet inventaire (`cavites_connues`) → pousse le
   package sur QFieldCloud.
3. Terrain : saisie dans QField → sync cloud.
4. Au bureau : sync du projet cloud (récupère les cavités terrain).
5. *Synchroniser le retour terrain* : `GeoPackage QField` = le gpkg cloud,
   **`GeoPackage principal` laissé vide**, `Promouvoir` coché, cible = le gpkg
   inventaire séparé. → cavités promues + localisation géocodée.
6. La prochaine prép relit l'inventaire enrichi : le scoring est à jour
   automatiquement (pas d'étape manuelle).

**Modèle « un seul gpkg »** (variante) : tu peux garder l'inventaire dans le gpkg
principal (couche `cavites_connues`) — pointe ce gpkg comme cible, `cavites_connues`
est créée si absente. ⚠️ « Préparer une sortie » régénère le gpkg et **écrase**
`cavites_connues` : avec ce modèle, ne relance pas la prép sur ce gpkg. Si la
cible est absente ou invalide, la promotion est refusée et le tampon `cavites`
est conservé.

---

### Mettre à jour les cibles après retour terrain

**Traitement → Boîte à outils → KarstPro → Mettre à jour les cibles**

Une fois le GPKG synchronisé depuis QField, cet algorithme lit les cavités
saisies sur le terrain (couche `cavites`) et **retire automatiquement des couches
P1/P2/P3 les cibles qui ont été prospectées**.

| Paramètre | Description |
|-----------|-------------|
| GeoPackage du secteur | Le `.gpkg` synchronisé après retour terrain |
| Couche des cavités à retirer | **Liste déroulante** des couches ponctuelles du projet. Choisir la couche de référence des points prospectés : **`cavites`** (saisies QField) ou **`cavites_connues`** (cavités déjà répertoriées). Laisser vide = couche `cavites` du GeoPackage par défaut. Si la couche choisie est vide, l'outil signale les autres couches de cavités peuplées. |
| Buffer GPS | Rayon en mètres autour du point GPS saisie pour compenser l'imprécision GPS (défaut : 15 m) |
| Nom du secteur *(avancé)* | **Auto-détecté** depuis les couches du GPKG — laisser vide. À renseigner uniquement si plusieurs jeux de cibles coexistent dans le même fichier. |

**Méthode de détection :** l'algorithme recourt aux **polygones de dolines** (couche `dolines`) plutôt qu'à une simple distance au centroïde. Chaque point GPS saisie est élargi du buffer GPS, puis intersecté avec les polygones — une cavité saisie n'importe où dans la doline (ou juste à son bord avec l'imprécision GPS) déclenche la suppression de la cible correspondante.

**Résultat :**
- Les couches P1/P2/P3 du GPKG sont mises à jour en place
- La log affiche chaque doline visitée détectée
- **Recharger les couches dans QGIS** après exécution (clic droit → Actualiser)

> **Workflow recommandé :**
> 1. Retour terrain → synchroniser QField vers le GPKG
> 2. Lancer **Mettre à jour les cibles** → les dolines visitées disparaissent des
>    couches `<secteur> — cibles P1/P2/P3` (affichage QGIS/QField)
>
> Note : **l'export MLL lit la couche `dolines` et recalcule les priorités depuis
> le `score`** — son rapport porte donc sur toutes les dolines scorées, pas
> seulement sur les cibles restantes après prospection.

---

## Format topo supporté

Visual Topo (`.tro`/`.trox`) → dans Visual Topo : **Fichier → Exporter → Shapefile ou KML**
→ importer le fichier `.shp` ou `.kml` dans KarstPro comme "Topo réseau existant".

> Les exports KML de Visual Topo contiennent des polygones de galeries — KarstPro les convertit
> automatiquement en polylignes pour le calcul de distance.

---

## Scoring des dolines

### Priorités

| Couleur | Score v2 | Signification |
|---------|----------|---------------|
| 🔴 Rouge | **≥ 55** | Très fort intérêt spéléologique — à visiter en priorité (P1) |
| 🟠 Orange | **35–54** | Bon intérêt — cible secondaire (P2) |
| 🟡 Jaune | 25–34 | Intérêt modéré — à noter si passage (P3, masqué par défaut) |
| ⚫ Gris | < 25 | Faible intérêt — exclu des cibles terrain |

> **Seuils recalibrés v2** : abaissés de 10 pts par rapport à v1 (65/45/25 → 55/35/25)
> pour compenser la suppression des composantes non-discriminantes en v2
> (cold_air + circularité + densité retirées = 20–33 pts en moins en moyenne).
> Le seuil P3 de 25 est inchangé — il correspond à la limite de détectabilité LiDAR.

### Architecture du score

Le score repose exclusivement sur le **Bloc A — Morphologie** :

```
Score final = Bloc A (morphologie intrinsèque)   [0–100]
```

La topographie souterraine, si fournie, renseigne les colonnes informatives
`comp_dist_reseau_m` et `comp_in_couloir` mais **n'intervient pas dans le calcul
du score ni des priorités**.

> **Pourquoi ce choix ?** Voir section *Validation IKarre* ci-dessous.

---

### Bloc A — Morphologie (v2.0)

*Mesure la forme intrinsèque de la doline, indépendamment de sa localisation.*

**Tableau récapitulatif des composantes v2 :**

| Composante | Max | Statut |
|------------|-----|--------|
| Surface | 10 | En score |
| Profondeur | 30 | En score — continu au-delà de 8 m |
| Ratio P/√S | 8 | En score — réduit (v2) |
| Pente bord | 20 | En score — p90 anneau 5 m (v2) |
| Liseré | 10 | En score — rayon 100 m / 20° (v2) |
| Absorption D8 | 18 | En score — réduit (v2) |
| Contact géologique | 25 | En score — facteur karstifiabilité (v2) |
| TPI 500 m | 8 | En score — NOUVEAU (v2) |
| Cold air index | — | **Informatif uniquement** (v2) |
| Circularité | — | **Informatif uniquement** (v2) |
| Densité 500 m | — | **Informatif uniquement** (v2) |
| **TOTAL MAX THÉORIQUE** | **129** | Clippé à 100 |

---

**Surface** — max 10 pts

La taille de l'entrée conditionne l'accessibilité et la quantité d'eau absorbée.
Les très grandes dolines (> 1 500 m²) sont des pertes potentielles majeures mais
reçoivent un poids limité car la surface seule est peu discriminante.

| Seuil | Points |
|-------|--------|
| < 50 m² | 2 |
| 50 – 300 m² | 5 |
| 300 – 1 500 m² | 8 |
| > 1 500 m² | 10 |

---

**Profondeur** — max **30 pts** — *(augmenté en v2, mode continu)*

Composante à plus fort poids. Une doline profonde indique un vide sous-jacent
significatif et/ou une dissolution active. La courbe est délibérément raide.

En v2, le score est **continu au-delà de 8 m** : plutôt qu'un plafond abrupt à 22 pts,
chaque mètre supplémentaire rapporte +0,4 pt, jusqu'à un plafond de 30 pts à 28 m.
Cette correction élimine la discontinuité qui faisait stagner les gouffres de 8–20 m.

| Seuil | Points |
|-------|--------|
| < 0,3 m | 1 |
| 0,3 – 1,0 m | 6 |
| 1,0 – 3,0 m | 13 |
| 3,0 – 8,0 m | 22 |
| > 8,0 m | 22 + (prof − 8) × 0,4, plafond **30 pts** |

---

**Ratio P/√S** — max **8 pts** — *(réduit depuis 12, v2)*

*Potentiel vertical = profondeur / √surface*

Mesure le caractère "plongeant" de la doline indépendamment de sa taille absolue.
Réduit en v2 car partiellement redondant avec la profondeur (ScoringReview 2026).

| Seuil | Points |
|-------|--------|
| < 0,1 | 0 |
| 0,1 – 0,2 | 3 |
| 0,2 – 0,4 | 6 |
| > 0,4 | 8 |

---

**Densité locale 500 m** — *INFORMATIVE UNIQUEMENT (hors score en v2)*

Le nombre de dolines voisines dans un rayon de 500 m est stocké dans la colonne
`comp_densite_500m` mais n'est plus compté dans le score. Dans le Barrois (> 300 dolines/km²),
le critère saturait pour toute la zone (> 50 voisines = 15 pts pour tout le monde)
et n'apportait aucune discrimination (ScoringReview 2026).

---

**Bassin versant amont** — **18 pts** — *(réduit depuis 25, v2)*

Surface drainée vers la doline depuis l'amont, calculée depuis le raster de flow
accumulation D8 (1 cellule = 1 m²). Une doline qui capte un bassin de 3 ha n'est
pas la même chose qu'une dépression fermée de 200 m².

| Bassin versant amont | Points | Classification automatique |
|----------------------|--------|---------------------------|
| < 1 000 m² | 0 | `doline` — dépression fermée isolée |
| 1 000 – 5 000 m² | 6 | `doline` — drainage local modeste |
| 5 000 – 20 000 m² | 12 | `doline-perte` — captage significatif |
| > 20 000 m² (2 ha) | 18 | `perte` — perte active avec chenal probable |

La colonne `type_doline` est renseignée automatiquement dans la couche `dolines`.

---

**Contact géologique** — 25 pts + facteur karstifiabilité *(v2)*

La doline se situe sur une formation karstique reconnue (calcaire ou dolomie).
Source : BD Charm-50 1/50 000 (cache local auto-téléchargé).

En v2, un **facteur multiplicatif de karstifiabilité** est appliqué selon le code
lithologique `CODE_LEG` du polygone. Cela permet de différencier les calcaires sans
modifier la géométrie BD Charm-50.

| Code | Lithologie | Facteur |
|------|-----------|---------|
| j4–j9 | Calcaires jurassiques (Oxfordien, Tithonien…) | 1,0 |
| j1–j3 | Calcaires Bathonien/Bajocien (moins karstifiés) | 0,9 |
| c1 | Craie Albienne | 0,4 |
| c2–c5 | Craies Cénomaniennes–Campaniennes | 0,5 |
| c6–c7 | Craies peu karstifiées | 0,3 |
| e | Éocène calcaire | 0,7 |
| t | Turonien | 0,6 |
| *autres* | Défaut | 1,0 |

Le gradient exponentiel (constante 250 m) est appliqué **avant** le facteur :
`score = 25 × exp(−dist_bord / 250) × facteur_karstifiabilité`.

---

**TPI 500 m** — max **8 pts** — *NOUVEAU composante v2*

*Topographic Position Index — altitude de la doline vs. moyenne des voisines à 500 m.*

Une doline sommitale (altitude supérieure à ses voisines) est en position d'absorption
directe : les eaux de pluie n'ont pas de relief intermédiaire pour les dérouter. Une
doline en fond de vallon a moins de potentiel d'absorption directe (elle reçoit surtout
le ruissellement concentré, déjà capté par le bassin versant D8).

| TPI (m) | Position | Points |
|---------|---------|--------|
| < −20 m | Fond de vallon | 0 |
| −20 à 0 m | Légèrement en creux | 3 |
| 0 à 20 m | Légèrement sommitale | 5 |
| > 20 m | Sommitale nette | 8 |

Calculé depuis la colonne `altitude_m` existante — pas de lecture MNT supplémentaire.

---

### Topo réseau — colonnes informatives (hors score)

Si une topo est fournie lors de la préparation, deux colonnes informatives sont
calculées dans la couche `dolines`. Elles n'affectent pas le score.

| Colonne | Contenu |
|---------|---------|
| `comp_dist_reseau_m` | Distance en mètres au passage topo le plus proche |
| `comp_in_couloir` | `True` si la doline est dans un couloir de galeries (buffer 500 m autour du réseau) |

Ces colonnes sont utiles pour croiser manuellement le scoring avec la topographie
connue dans QGIS ou dans l'analyse MLL.

---

### Validation IKarre — résultats v2 (scoring + seuils recalibrés)

La méthode a été validée sur **130 cavités spéléologiques réelles** issues de la
base IKarre (inventaire spéléologique régional), sur 3 communes du Grand Est.
Les chiffres ci-dessous correspondent au scoring v2.0 avec les seuils recalibrés
(P1 ≥ 55, P2 ≥ 35, P3 ≥ 25) — voir section *Scoring refactor v2* pour le détail.

| Commune | Dept. | Cavités | Rappel P1+P2 | z (vs aléatoire) | Rôle |
|---------|-------|---------|--------------|------------------|------|
| Trois-Fontaines-l'Abbaye | Marne 51 | 70 | 54,3 % | 3,9 | calibration |
| Sommelonne | Meuse 55 | 25 | 32,0 % | 4,7 | calibration |
| Ancerville | Meuse 55 | 35 | 28,6 % | 2,9 | calibration |
| **Pierre-la-Treiche** | M-&-M 54 | 67 | 38,8 % | **1,1** | **hors-échantillon** |
| **Lisle-en-Rigault** | Meuse 55 | 102 | 23,5 % | **−0,7** | **hors-échantillon** |

Rappel mesuré à un rayon de correspondance de **50 m**. Le `z` mesure l'écart au
modèle nul (permutation des labels) : z ≥ 2 = signal réel.

> **⚠️ Le score à poids manuels NE généralise PAS.** Les trois communes de
> calibration affichent un z fort (2,9–4,7), mais les deux communes jamais vues
> retombent au niveau du hasard (z ≤ 1,1 ; Lisle, même karst que la calibration,
> est même légèrement sous le hasard). C'est la signature d'un **sur-ajustement**
> des seuils sur leurs propres données. La priorisation P1/P2/P3 doit être
> considérée comme **exploratoire**, non comme une capacité prédictive validée.

**Ce qui EST validé (leave-one-commune-out, 5 communes) :**

- Le **signal morphométrique existe et généralise** dans un même domaine
  géologique : une pondération *apprise* (régression logistique, `prototypes/`)
  atteint **AUC 0,72** hors-échantillon sur le Barrois, contre **0,56** pour les
  poids manuels actuels. → les poids sont à refaire, l'idée tient.
- La généralisation **s'arrête à la frontière géologique** : un modèle Barrois
  appliqué au bajocien (Pierre-la-Treiche) retombe à AUC 0,45. Un modèle par
  massif est nécessaire.
- L'**inventaire LiDAR des dolines** et le **workflow terrain QField** sont, eux,
  pleinement opérationnels et indépendants de la qualité du score.
- La topo testée sur Ancerville (261 passages, réseau réel) **n'a modifié aucune
  priorité** sur les 35 cavités IKarre.
- **~18 % de cavités IKarre restent hors-seuil (< 25) toutes communes confondues** :
  ces cavités n'ont pas d'empreinte morphologique détectable dans le LiDAR 1 m
  (entrée ponctuelle, remplissage, épikarst). C'est la limite physique de la méthode,
  non améliorable par le scoring.

**Pourquoi le Bloc B a été supprimé :** le score positionnel médian des cavités
IKarre matchées sur Ancerville (261 passages topo) était de 5,2/100 — insuffisant
pour franchir un seuil. La formule de mélange 50/50 *dégradait* les scores dans
les zones peu explorées, précisément les zones cibles d'une prospection.

**Conclusion :** le Bloc A seul est plus robuste, plus universel, et valide
empiriquement sur le jeu de données disponible.

---

### Cavités connues — `cavite_connue_proche` (informatif, hors score)

Si une couche de cavités connues est fournie lors de la préparation, **et/ou** si des
cavités Géorisques BRGM ont été téléchargées automatiquement, chaque doline reçoit
les colonnes suivantes dans la table attributaire.

| Colonne | Contenu |
|---------|---------|
| `cavite_connue_proche` | `True` si une cavité connue est à moins de 20 m du centroïde |
| `cavite_distance_m` | Distance en mètres à la cavité connue la plus proche (**toujours** renseignée — loin de tout = territoire vierge) |
| `cavite_nom` | Nom de la cavité liée — **uniquement si elle est proche** (≤ 20 m), sinon vide |
| `cavite_type` | Type de la cavité liée (sinon vide) |
| `cavite_ref` | Référence de la cavité liée (sinon vide) |

`cavite_nom`/`type`/`ref` ne sont remplis **que lorsqu'une cavité connue est
réellement proche** : sans cela, une doline à 1 km d'une cavité « référencerait »
celle-ci, ce qui prête à confusion. Pour une doline lointaine, on ne garde donc
que la distance et le flag.

**Préférence inventaire.** Quand une cavité est proche, KarstPro lie en priorité
une cavité de **ton inventaire** (`cavites_connues`, noms/réfs fiables) si elle est
dans le rayon, plutôt qu'une cavité Géorisques « anonyme » même légèrement plus
proche. Géorisques sert alors de repli quand aucune cavité d'inventaire n'est à
proximité.

Les colonnes acceptées dans la couche utilisateur : `name`, `type`, `date_disc`, `date_expl`,
`explorers`, `comment`, `reference`. Les colonnes absentes sont ignorées silencieusement.

Les cavités Géorisques sont normalisées automatiquement (`nom_cavite → name`,
`type_cavite → type`, `identifiant → reference`) avant la fusion.

Le rayon de **20 m** correspond à la marge d'erreur GPS + imprécision de pointé.
Dans un karst sous couverture (Barrois), deux dolines à 25 m peuvent alimenter des
conduits distincts — 20 m est volontairement conservateur pour ne pas masquer des
cibles légitimes dans les alignements denses.

> **Les dolines marquées `cavite_connue_proche = True` restent dans les couches P1/P2/P3.**
> La proximité d'une cavité connue n'entraîne aucune suppression automatique — une cavité
> "connue" peut être peu ou anciennement explorée, ou correspondre à une entrée distincte
> du même phénomène. Les dolines concernées sont signalées 🏛️ dans le rapport MLL ;
> c'est le spéléologue qui décide de les déprioritiser au cas par cas.

> Ce flag est **hors score** — une doline à 15 m d'une grotte connue peut être
> une entrée alternative ou un prolongement non exploré. La décision est laissée
> au spéléologue, aidé par l'analyse MLL.

---

### Scoring refactor v2 — Rationale et évolution (ScoringReview 2026)

Cette section documente les décisions prises lors de la revue de scoring v2 (2026).

**Composantes supprimées du score :**

| Composante | Raison de la suppression |
|-----------|--------------------------|
| Cold air index | Redondant avec `profondeur_m` et `ratio_ps` — mesure la même chose en passant par la courbure MNT. Triple comptage injustifié. |
| Circularité | Contre-productive pour le Barrois : les dolines structurales allongées (le long du contact) sont exactement les plus intéressantes, et une circularité basse les pénalisait. |
| Densité 500 m | Non-discriminante en Barrois dense : > 50 voisines dans tout le secteur → 15 pts pour tout le monde, aucune séparation. |

**Composantes modifiées :**

| Composante | Modification | Justification |
|-----------|-------------|---------------|
| Profondeur | Max 22 → 30 pts, mode continu > 8 m | Gouffres 8–20 m stagnaient au même score que les dolines de 8 m. |
| Ratio P/√S | Max 12 → 8 pts | Partiellement redondant avec profondeur — réduction sans suppression. |
| Absorption | Max 25 → 18 pts | Réduction pour rééquilibrer la somme après suppression des autres composantes. |
| Pente bord | max → p90, anneau 3 → 5 m | Robustesse aux artefacts LiDAR ponctuels. |
| Liseré | Hors score → 10 pts en score (critères resserrés 100 m/20°) | Signal structurel confirmé sur terrain Barrois. |

**Composante ajoutée :**

| Composante | Justification |
|-----------|---------------|
| TPI 500 m (8 pts) | Différencie les dolines sommitales (absorption directe) des dolines en fond de vallon. Information absente de toutes les autres composantes. |

**Impact attendu sur le rappel IKarre :**
Les simulations analytiques sur les 3 communes de validation (Trois-Fontaines, Sommelonne,
Ancerville) prévoient un rappel P1+P2 stable ou légèrement amélioré, avec une meilleure
précision (moins de faux positifs liés à la circularité et à la densité).

---

### Pente des bords — `pente_max_bord` — max 20 pts *(v2 : p90, anneau 5 m)*

*Signal de soutirage actif, calculé depuis le MNT LiDAR 1 m. Intégré au Bloc A.*

Un versant subvertical (> 70°) indique un effondrement récent — parois raides, fond
affaissé brutalement. Un effondrement ancien stabilisé présente des bords adoucis (< 20°).

**Changements v2 :** anneau élargi de 3 à **5 m**, et passage du maximum brut au
**90e percentile** pour filtrer les artefacts ponctuels (arbres en bordure, piquets).

| Pente p90 bord | Points |
|----------------|--------|
| < 20° | 0 |
| 20° – 45° | 5 |
| 45° – 70° | 12 |
| > 70° | 20 |

Le score plafonne à 100 pts (somme théorique v2 : 129 pts).

---

### Liseré — `lisere` — **10 pts, EN SCORE depuis v2**

*Alignement directionnel dans le karst de contact du Barrois.*

Dans le Barrois, les dolines de soutirage se regroupent en liserés sinueux qui suivent
la trace du contact lithostratigraphique calcaires tithoniens / argiles néocomiennes.
La colonne `lisere` (booléen) indique si la doline appartient à un tel alignement.
**Le bonus est inclus dans le score depuis v2.**

**Critères v2 (resserrés) :** ≥ 3 voisines dans **100 m** (était 200 m) avec
écart-type circulaire d'azimut < **20°** (était 30°) — statistique directionnelle
mod 180° (von Mises). Le bonus est de **10 pts** (était 15 pts).

Les critères resserrés visent à exclure les regroupements diffus non-structuraux.
Dans les zones à densité > 100 dolines/km², les critères v1 accordaient le bonus à
trop de dolines pour qu'il soit discriminant.

---

### Altitude — `altitude_m`

*Extraite automatiquement du MNT IGN 1 m au centroïde de chaque doline.*

Altitude en mètres NGF du fond de la dépression détectée. Utilisée pour :
- calculer le TPI 500 m (composante de score v2) ;
- le raisonnement hydrogéologique (niveau de base, niveaux perchés) ;
- l'organisation de la prospection par dénivelé de marche.

---

### Indice de piégeage d'air froid — `cold_air_index` — **INFORMATIF UNIQUEMENT (v2)**

*Calculé automatiquement depuis le MNT LiDAR 1 m. Hors score depuis v2.*

**Principe physique :** l'air froid s'accumule dans les dépressions fermées. Une cavité
avec courant d'air actif crée en hiver un échange thermique détectable (ressuage, gel
localisé, courant d'air sensible à la main).

```
cold_air_index = 0,55 × confinement_norm + 0,45 × concavité_norm  ∈ [0, 1]
```

> Ce critère est **hors score depuis v2** (ScoringReview 2026) : il est fortement
> corrélé à `profondeur_m` et `ratio_ps` — inclus dans le score, il créait une triple
> redondance. La colonne est conservée dans le GPKG pour analyse terrain.

La symbologie est embarquée dans le GeoPackage — les couleurs s'appliquent automatiquement
à l'ouverture dans QGIS.

**Couche MNT en ombrage** : le projet `.qgs` généré inclut automatiquement le MNT
(`lidar_work/mnt.tif`) en **ombrage multidirectionnel** + rééchantillonnage
bilinéaire, placé sous les couches vecteur — pour repérer visuellement dolines et
dépressions. Cette couche est **exclue du packaging QField** (raster trop lourd
pour le téléphone) et n'apparaît que dans le projet bureau. Si `mnt.tif` est
absent, la couche est simplement omise.

> **Important — ouvrir le `.qgs`, pas le `.gpkg` :** la couche MNT (raster
> externe référencé) et le rendu des courbes de niveau (maîtresses en gras +
> étiquettes) vivent dans le **projet `.qgs`**. Ouvre `<secteur>.qgs` pour les
> voir. Le style des courbes n'est pas persisté dans le `.gpkg` (cela ouvrirait
> le GeoPackage en mode WAL et laisserait des fichiers `.gpkg-wal`/`.gpkg-shm`).

**Zoom initial** : à l'ouverture, le projet `.qgs` se cadre automatiquement sur
l'emprise des **cibles P1** (rouges), avec une petite marge — pas besoin de
chercher la zone sur une carte vide. Si aucune cible P1, il se cadre sur
l'ensemble des dolines.

**Fond de plan IGN** : le projet `.qgs` ajoute aussi le **Plan IGN** (WMS
Géoplateforme `GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2`) tout en bas de l'arbre des
couches, **visible par défaut** comme fond de carte (nécessite une connexion
internet). L'ombrage MNT au-dessus est réglé à **70 % d'opacité** pour laisser
transparaître le Plan IGN tout en gardant le relief lisible. Exclu du packaging
QField.

---

## Export pour analyse MLL (IA)

**Traitement → Boîte à outils → KarstPro → Exporter pour analyse MLL**

**Paramètres requis** (toujours visibles) :

| Paramètre | Description |
|-----------|-------------|
| GeoPackage KarstPro | Le `.gpkg` du secteur |
| Dossier de sortie | Par défaut : dossier du `.gpkg` |

**Paramètres optionnels** — regroupés dans la section **« Paramètres avancés »**,
repliée par défaut :

| Paramètre | Description |
|-----------|-------------|
| Nom du secteur | Nom affiché dans le rapport (auto-détecté si laissé vide) |
| Contexte terrain | Texte libre : géologie locale, historique explorations… |
| Direction du pendage / sens de drainage | **Laisser vide = estimation automatique** depuis la couche `geologie` + le MNT (voir ci-dessous). Renseigner pour forcer une valeur manuelle (ex. `NNE vers la vallée de l'Aube`). |
| Zones à exclure | Ex. `quadrant sud — falaises, propriété privée` |

> **Traçages hydrologiques** : si une couche `tracages` est présente dans le gpkg
> (copiée à la préparation depuis `Inventaire Traçages` de Karst Entry), les
> connexions perte→résurgence sont automatiquement injectées dans le prompt MLL
> avec les coordonnées L93 des extrémités, pour l'interprétation hydrologique des
> cibles. Aucun paramètre à renseigner — c'est lu depuis le gpkg.

#### Estimation automatique du pendage

Si le champ **Direction du pendage** est laissé vide, KarstPro l'estime par la
méthode du **problème des trois points** :

1. il prend chaque contact entre deux formations géologiques (couche `geologie`) ;
2. il échantillonne l'altitude du **MNT** (`lidar_work/mnt.tif`, à côté du `.gpkg`)
   le long de la trace du contact ;
3. il ajuste un plan sur les points (x, y, z) → **azimut et angle de pendage**.

Le contact le mieux ajusté (R² le plus élevé, après filtrage des tracés plats ou
des discordances) est retenu. Le résultat injecté dans le prompt MLL ressemble à :
`WNW (~302°), pendage faible ~0,8° (estimé auto. depuis géologie + MNT)`.

> **Limites :** fiable sur un monocline doux et bien contrasté (ex. Barrois,
> R² ~0,9). Si aucun contact conformable exploitable n'est trouvé, ou si le MNT
> est absent, le champ reste vide (aucune valeur inventée). Renseigner
> manuellement le champ désactive l'estimation.

### Fichiers générés

Un sous-dossier `mll_export_<secteur>_<date>/` est créé :

```
MonSecteur/
  MonSecteur.gpkg              ← couches P1/P2/P3 (créées par la PRÉPARATION)
  MonSecteur.qgs
  mll_export_MonSecteur_2026-05-14/
    mll_prompt_MonSecteur_2026-05-14.txt   ← à coller dans MLL (rapport inclus)
    cibles_MonSecteur_2026-05-14.gpx          ← waypoints GPS
    mll_export_MonSecteur_2026-05-14.log      ← journal complet de l'export
```

| Fichier | Contenu |
|---------|---------|
| `mll_prompt_…txt` | Prompt complet à coller dans MLL — **rapport intégral embarqué** (clusters, tableaux enrichis altitude/absorption/géologie/dist. réseau, JSON brut) + instructions de génération |
| `cibles_…gpx` | Waypoints rouge + orange (WGS84) avec score, profondeur, ratio P/√S et air froid dans la description — Garmin, OruxMaps, CalTopo… |
| `mll_export_…log` | Journal complet de l'export (versions, paramètres, pendage auto-estimé + R², avertissements, durée) — persiste même si la boîte de dialogue est fermée |

> **Note :** l'export MLL ne touche **pas** au GeoPackage. Les couches
> `<secteur> — cibles P1/P2/P3` sont créées et peuplées **uniquement par la
> préparation**. L'export ne produit que le rapport, le prompt et le GPX.

### Couches P1 / P2 dans QGIS et QField

Les couches P1/P2/P3 sont créées et peuplées **à la fin de la préparation**
(centroïdes des dolines scorées). L'export MLL ne les modifie pas ; l'ordre de
visite optimisé est proposé par MLL dans le GPX/rapport qu'il génère en retour.

- **P1** (rouges, score ≥ 55) et **P2** (oranges, score 35–54) : visibles dans QGIS et QField
- **P3** (jaunes, score 25–44) : masquée par défaut — à activer dans le panneau de couches si besoin
- Champs de scoring (lecture) : `score`, `priorite`, `profondeur_m`, `surface_m2`,
  `ratio_ps`, `cold_air_index`
- Champs terrain (éditables après visite) : `type`, `comment`,
  `developpement_estime`, `topographiable`, `lien_topo`, plus `name`, `reference`
- Ces couches sont **en lecture seule** dans QField (pas de saisie GPS dessus —
  utiliser `cavites` pour enregistrer une découverte)

### Utilisation du GPX

Le fichier `.gpx` contient un waypoint par doline rouge et orange :
- **Nom** : `doline_<ID>_R` (rouge, ≥ 55) ou `doline_<ID>_O` (orange, 35–54)
- **Description** : score, surface, profondeur, ratio P/√S, indice air froid
- **Import** : Garmin BaseCamp, OruxMaps (Android), CalTopo, IGNrando, GaiaGPS…

### Utilisation du prompt MLL

1. Ouvrir votre interface MLL dans le navigateur ou l'application
2. **Joindre le fichier `.gpkg`** en pièce jointe (icône trombone) — permet à MLL d'accéder aux données brutes en complément du rapport embarqué dans le prompt
3. Ouvrir `mll_prompt_<secteur>_<date>.txt` dans un éditeur
4. Sélectionner tout (`Ctrl+A`) → copier → coller dans MLL
5. MLL retourne :
   - Liste priorisée des cibles terrain (regroupées géographiquement)
   - Analyse structurale du karst (alignements, concentrations)
   - Recommandations pratiques par type de phénomène
   - Un fichier GPX ordonné (ordre de visite optimal, pas par score brut)
   - Un CSV importable dans QGIS avec types supposés et notes terrain
   - **Un script Python à exécuter pour générer le rapport DOCX** (voir ci-dessous)

### Rapport DOCX — généré via le script Python de MLL

MLL produit un script Python autonome utilisant `python-docx`. Pour l'utiliser :

```bat
pip install python-docx
python rapport_<secteur>.py
```

Le fichier `rapport_<secteur>_<date>.docx` est créé dans le dossier courant. Il contient :

| Section | Contenu |
|---------|---------|
| Page de titre | Secteur, date, nombre de cibles rouges / oranges / jaunes |
| Résumé exécutif | Contexte, potentiel estimé, points clés de l'analyse |
| Tableau des cibles | Toutes les rouges + top 20 oranges — coords GPS WGS84, profondeur, score, type supposé, indice terrain |
| Organisation | Planning par journées avec l'ordre de visite optimal |
| Analyse structurale | Alignements, direction de drainage, zones de prolongement |
| Recommandations | Matériel, conditions, signes à rechercher sur place |
| Fiches terrain | Une fiche vierge par cible rouge (ID, coords, cases observation / résultat) |

> Les données (coordonnées, scores, types supposés) sont écrites en dur dans le script — il est donc autonome et reproductible, sans dépendance vers le GPKG.

### Ce que contient le rapport

- Résumé du secteur (nb dolines, réseau connu, observations terrain, cavités connues)
- **Section "Clusters géographiques"** : regroupement automatique des dolines rouges + oranges
  par connexité spatiale (seuil 400 m, algorithme Union-Find). Chaque cluster reçoit une lettre
  (A, B, C…), avec centroïde L93, altitude min–max et liste des membres. Utilisé par MLL
  comme base pour organiser les journées de prospection.
- **Tableaux rouges + top 30 oranges enrichis** : en plus du score et de la morphologie,
  chaque ligne affiche maintenant :
  - **Cluster** — lettre du groupe géographique
  - **Alt. (m)** — altitude du centroïde depuis le MNT
  - **Absorb.** — ✓ si bassin versant ≥ 5 000 m² (`doline-perte` ou `perte`)
  - **Géol.** — ✓ si le centroïde est sur une formation karstifiable (25 pts)
  - **Dist. réseau (m)** — distance au passage topo le plus proche
- **Section "Cibles de découverte" 🔍** : dolines avec profondeur ≥ 5 m et éloignées du réseau connu (pas de topo, ou distance > 500 m) — fort signal morphologique sans association au réseau, donc zones sous-explorées à prioriser, triées par profondeur décroissante
- **Section "Cavités connues" 🏛️** : deux tableaux distincts — (1) cavités fournies par l'utilisateur (nom, type, dates, explorateurs, référence) et (2) cavités BRGM Géorisques (nom, type, identifiant, date de validité, repérage). Note à MLL : les points Géorisques sont des données d'inventaire administratif, moins fiables géométriquement que les données utilisateur.
- JSON brut de toutes les dolines — inclut `altitude_m`, `bassin_versant_m2`, `type_doline`,
  `comp_absorption`, `comp_geologie`, `comp_geologie_dist_m`, `comp_dist_reseau_m`,
  `comp_in_couloir`, `comp_densite_500m` pour une analyse complète des composantes du score
- Note explicite à MLL sur les cibles de découverte (dolines profondes hors réseau connu)
- Section clusters pré-calculés dans le prompt pour que MLL organise directement par journée

---

# Troubleshooting

## Géorisques — couche `cavites_georisques` absente ou vide

**Symptôme :** Le GPKG ne contient pas de couche `cavites_georisques`, ou la couche
est présente mais vide alors qu'Infoterre affiche des cavités sur la zone.

**Causes possibles :**

1. **Bbox mal positionnée** — Le WFS Géorisques utilise les coordonnées de la zone
   dessinée dans QGIS. Vérifier que le projet QGIS est en EPSG:2154 ou que la
   reprojection automatique s'est bien déclenchée (voir la log QGIS).

2. **Base Géorisques lacunaire dans la zone** — La base nationale des cavités
   (`CAVITE_LOCALISEE`) est exhaustive dans les grands massifs calcaires (Dordogne,
   Jura, Ardèche) mais peu renseignée dans les karsts sous couverture
   (Champagne-Ardenne, Lorraine). Ce message dans la log est normal :
   ```
   Géorisques : aucune cavité référencée dans la zone
   ```

3. **Données Infoterre ≠ Géorisques** — Infoterre affiche aussi les forages BSS
   (Banque du Sous-Sol) qui ne sont pas des cavités spéléologiques. Seules les
   entrées de type `CAVITE_LOCALISEE` (cavités souterraines non minières) sont
   importées par KarstPro.

4. **Service Géorisques temporairement indisponible** — Le message dans la log sera :
   ```
   Géorisques ignoré : ...
   ```
   Relancer l'algorithme résout généralement le problème.

---

## Téléchargement LiDAR — dalles trop lentes

**Symptôme :** Le téléchargement avance mais prend 30–60 min pour 10–20 dalles.
Le CDN IGN bride les téléchargements automatisés sur `data.geopf.fr`.

**Solution — téléchargement manuel via gestionnaire de téléchargement :**

1. Lancer une première fois **Préparer une sortie** — même si c'est lent, KarstPro
   génère immédiatement un fichier `dalles_a_telecharger.txt` dans le dossier
   `<sortie>/lidar_work/laz/` et affiche son chemin dans la log QGIS.
2. Annuler l'algorithme si souhaité.
3. Ouvrir `dalles_a_telecharger.txt` — il contient une URL par ligne.
4. Coller les liens dans un gestionnaire de téléchargement
   (**Free Download Manager**, **JDownloader**, ou `wget -i dalles_a_telecharger.txt`)
   — généralement 5–10× plus rapide qu'via l'API.
5. Déposer les fichiers `.copc.laz` téléchargés dans le dossier `lidar_work/laz/`
   (même dossier que le fichier `.txt`), **sans renommer les fichiers**.
6. Relancer **Préparer une sortie** — KarstPro détecte les fichiers complets et
   passe directement à la génération MNT sans re-télécharger.

> Les dalles déjà en cache sont réutilisées automatiquement pour toute zone
> qui chevauche un secteur déjà traité.

---

## Téléchargement LiDAR — `IncompleteRead` / connexion coupée

**Symptôme :** Le téléchargement d'une dalle s'interrompt avec une erreur
`IncompleteRead` ou `ChunkedEncodingError`. Le CDN IGN (`data.geopf.fr`) coupe
la connexion en milieu de téléchargement, surtout sur les grosses dalles (> 100 MB)
et après un burst de téléchargements parallèles.

**Solution intégrée :** Le téléchargement reprend automatiquement là où il s'est
arrêté (header `Range`) avec jusqu'à 15 tentatives et un backoff exponentiel
(2ˢ secondes entre chaque essai, plafonné à 60 s). Aucune action requise pendant
les tentatives — laisser tourner.

**Si l'erreur persiste après 15 tentatives :** KarstPro affiche un message clair :

```
⚠ Échec définitif : LHD_FXX_xxxx_xxxx_….copc.laz
RuntimeError: 1 dalle(s) impossible(s) à télécharger (CDN IGN instable)
Solution : télécharger manuellement via dalles_a_telecharger.txt ...
URLs : https://data.geopf.fr/telechargement/…
```

Suivre la procédure de téléchargement manuel (voir section ci-dessus) :
ouvrir `lidar_work/laz/dalles_a_telecharger.txt`, copier l'URL de la dalle
en échec, la télécharger via navigateur ou gestionnaire de téléchargement,
déposer le `.copc.laz` dans le dossier `laz/`, puis relancer KarstPro.
Les dalles déjà complètes en cache ne sont pas re-téléchargées.

---

## Téléchargement LiDAR — HTTP 502 Bad Gateway

**Symptôme :**
```
RuntimeError: Échec téléchargement ... LHD_FXX_…copc.laz : HTTP 502
```

**Cause :** Erreur transitoire côté serveur IGN (surcharge, redémarrage de nœud CDN).

**Solution intégrée :** Les codes HTTP 429, 500, 502, 503, 504 déclenchent automatiquement
une nouvelle tentative avec backoff exponentiel, jusqu'à 15 essais. Le 502 ne provoque
plus d'arrêt immédiat.

**Si l'erreur persiste :** Attendre quelques minutes et relancer. Les dalles déjà présentes
sur disque sont réutilisées.

---

## Export MLL — aucun fichier créé, pas de sous-dossier

**Symptôme :** L'algorithme se termine sans erreur visible mais le dossier
`mll_export_<secteur>_<date>/` n'est pas créé.

**Cause :** Les fichiers du plugin en cours de développement (`Projects/karstpro/`)
ne sont pas synchronisés avec le dossier plugins QGIS
(`%APPDATA%\QGIS\QGIS4\profiles\default\python\plugins\karstpro\`).
QGIS exécute l'ancienne version.

**Solution :**
```powershell
Copy-Item -Path ".\karstpro\*" `
  -Destination "$env:APPDATA\QGIS\QGIS4\profiles\default\python\plugins\karstpro\" `
  -Recurse -Force
```
Puis recharger le plugin dans QGIS (Plugin Reloader, ou redémarrer QGIS).

**Vérification :** Comparer la date de modification de
`%APPDATA%\…\plugins\karstpro\algorithms\karst_export_mll_algorithm.py`
avec celle du fichier source.

---

## Export MLL — erreur silencieuse sans message dans la log QGIS

**Symptôme :** L'algo se termine avec une icône d'erreur rouge mais la log QGIS
ne montre aucun détail utile.

**Cause :** Une exception Python non rattrapée dans `processAlgorithm` est avalée
par QGIS sans afficher la traceback.

**Solution intégrée :** `processAlgorithm` est enveloppé dans un `try/except` qui
affiche la traceback complète via `feedback.reportError(traceback.format_exc())`.
Consulter la fenêtre **Journal des messages** (Vue → Panneaux → Journal des messages)
→ onglet **Traitement** pour voir la cause réelle.

---

## Points QField sans coordonnées (n'apparaissent pas sur la carte)

**Symptôme :** Une cavité saisie dans QField apparaît dans la liste
des attributs mais pas sur la carte — les coordonnées sont NULL.

**Cause :** Sur les projets créés avant la version actuelle, la couche `cavites`
était déclarée en type géométrie générique `GEOMETRY` (au lieu de `POINT`).
QField ne la reconnaissait alors pas comme couche de points et n'attachait
aucune position GPS — seuls les attributs étaient enregistrés.

**Solution pour les nouveaux projets :** Relancer **Préparer une sortie** —
le `.gpkg` généré déclare `cavites` en `POINT` et le `.qgs` configure QFieldSync
avec `geomSource=gps`. Le point est placé automatiquement à la position GPS dès
l'ouverture du formulaire. Une contrainte bloque aussi l'enregistrement sans
géométrie (utile en cas de perte de fix GPS sous couvert forestier).

**Solution de contournement (projet existant) :** Dans QField, activer le GPS,
puis éditer le point sans coordonnées → bouton **"Snapper sur le GPS"** dans
le formulaire pour renseigner la géométrie manuellement.

**Pour les points déjà saisis sans coordonnées dans QGIS :** Les supprimer et
les ressaisir sur le terrain, ou les placer manuellement avec l'outil de
numérisation QGIS si la position est connue.
