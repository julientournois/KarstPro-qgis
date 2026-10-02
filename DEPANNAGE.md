# KarstPro — Dépannage

> Problèmes courants et solutions. Extrait de la documentation principale.

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

## Espagne — « PNOA 1 m indisponible », étude en 5 m

**Symptôme :** le journal annonce que les dalles PNOA n'ont pas pu être
téléchargées, puis bascule sur le MDT WCS 5 m. L'étude se termine mais ne
trouve presque aucune doline et **aucun gouffre**.

**Cause :** depuis le **2026-09-29**, le portail du CNIG exige une
vérification anti-robot (reCAPTCHA) pour télécharger. KarstPro ne la
contourne pas. Le relief 5 m qui sert de repli est un produit interpolé :
il n'a pas de trous de NODATA, et la détection des gouffres y est donc
structurellement muette — le journal l'écrit en clair
(« nuage de points brut indisponible »).

**Ce que coûte le repli**, mesuré sur des dolines réellement détectées en
1 m : Cangas de Onis −65 %, Isaba −93 %, Marnaval −86 %. Les gouffres
passent de 26 643 à 0. Autrement dit : une carte en 5 m est trompeuse, pas
seulement imprécise.

**Solution — récupérer les dalles par le panier du CNIG :**

1. Ouvrir `<sortie>/lidar_work/laz/dalles_a_telecharger.txt` : KarstPro y a
   écrit **un lien par dalle** de l'emprise.
2. Ouvrir chaque lien et cliquer l'icône **panier** (« Añadir a la cesta »),
   **pas** le bouton de téléchargement.
3. Ouvrir le panier, puis **« Descarga automática »** → le site rend un
   fichier `.jnlp`.
4. **Déposer ce `.jnlp` dans le dossier de l'étude**, puis relancer
   *Préparer une étude* : KarstPro l'ouvre pour vous.
5. **Open Web Start demande une confirmation** avant de lancer l'application
   « CNIG DESCARGAS » publiée par le *Centro Nacional de Información
   Geográfica* : accepter. C'est normal — l'archive Java est signée par le
   CNIG, et Java demande toujours l'accord de l'utilisateur avant d'exécuter
   une application signée venant du réseau. Ce n'est pas un avertissement de
   sécurité à craindre, mais il faut y répondre, sinon rien ne se télécharge.
6. L'application du CNIG demande un dossier de destination — indiquer celui
   que le journal affiche (`<sortie>/lidar_work/laz/`).
7. Relancer *Préparer une étude* une dernière fois : les dalles sont reprises
   (« cache OK ») et l'étude se fait en **1 m**.

**Deux points qui bloquent souvent :**

- **Au-delà de 20 dalles, il faut un compte CNIG** (gratuit) : c'est la
  limite du panier pour un visiteur non enregistré. Au-delà, le site affiche
  un message et refuse l'ajout. Avec un compte, la limite passe à 40 000.
- Le `.jnlp` s'ouvre avec **Open Web Start**
  (<https://openwebstart.com/download/>), qui remplace Java 8 depuis le
  2026-09-29. Sans lui, Windows ne saura pas quoi faire du fichier.

**Variante sans panier** (pour une petite emprise) : télécharger les dalles
une par une depuis les mêmes liens, et les déposer dans
`<sortie>/lidar_work/laz/` **sans renommer les fichiers** — le nom porte la
position de la dalle.

**Lequel des deux choisir ?** Pas pour la vitesse : le panier télécharge en
flux unique à **~1,8 Mio/s** (mesuré sur 16 dalles, soit ~6 min pour 620 Mo),
et un navigateur qui parallélise plusieurs fichiers n'est pas forcément plus
lent. Ce qui départage :

| | Un par un | Panier + `.jnlp` |
|---|---|---|
| Clics | ~2 par dalle | ~1 par dalle, puis 4 étapes |
| Où atterrissent les fichiers | dossier `Téléchargements` | **directement dans `lidar_work/laz/`** |
| Fichiers à déplacer à la main | **oui, tous** | aucun |
| Limite de nombre | aucune | 20 sans compte CNIG |
| Prérequis | aucun | Open Web Start |

Le déplacement des fichiers est l'étape où ça casse : un fichier oublié ou
renommé donne une couverture partielle **sans aucun message**. D'où la
recommandation du panier dès qu'il y a plus de quelques dalles — et le
un-par-un quand on ne veut ni compte ni Java.

**À éviter :** le champ « MNT pré-téléchargé(s) » accepte un raster et
court-circuite tout, mais il ne fournit **aucun nuage de points** : la
détection des gouffres et l'analyse du nuage brut restent inactives.

## Téléchargement LiDAR — dalles trop lentes

**Symptôme :** Le téléchargement avance mais prend 30–60 min pour 10–20 dalles.
Le CDN IGN bride les téléchargements automatisés sur `data.geopf.fr`.

**Solution — téléchargement manuel via gestionnaire de téléchargement :**

1. Lancer une première fois **Préparer une étude** — même si c'est lent, KarstPro
   génère immédiatement un fichier `dalles_a_telecharger.txt` dans le dossier
   `<sortie>/lidar_work/laz/` et affiche son chemin dans la log QGIS.
2. Annuler l'algorithme si souhaité.
3. Ouvrir `dalles_a_telecharger.txt` — il contient une URL par ligne.
4. Coller les liens dans un gestionnaire de téléchargement
   (**Free Download Manager**, **JDownloader**, ou `wget -i dalles_a_telecharger.txt`)
   — généralement 5–10× plus rapide qu'via l'API.
5. Déposer les fichiers `.copc.laz` téléchargés dans le dossier `lidar_work/laz/`
   (même dossier que le fichier `.txt`), **sans renommer les fichiers**.
6. Relancer **Préparer une étude** — KarstPro détecte les fichiers complets et
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

**Solution pour les nouveaux projets :** Relancer **Préparer une étude** —
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
