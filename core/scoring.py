# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
import json
from pathlib import Path
import geopandas as gpd
import numpy as np


def load_config(path: Path) -> dict:
    return dict(json.loads(Path(path).read_text()))


def score_to_priority(score: float) -> str:
    """Convertit un score v2 [0–100] en priorité terrain.

    Seuils recalibrés v2 (ScoringReview + validation IKarre 2026) :
      P1 (rouge)  ≥ 55      P2 (orange) ≥ 35      P3 (jaune)  ≥ 25

    ⚠️ AVERTISSEMENT VALIDATION (priorisation EXPLORATOIRE, non prédictive) :
    Ces seuils à poids manuels ont été calés sur 3 communes (z 2,9–4,7) mais NE
    GÉNÉRALISENT PAS : sur 2 communes hors-échantillon le classement retombe au
    niveau du hasard (AUC 0,56 ; cf. prototypes/loco_cv.py et dossier validation/).
    Le signal morphométrique existe néanmoins (AUC 0,72 hors-échantillon avec une
    pondération apprise par domaine géologique) → les poids sont à refaire.
    Utiliser P1/P2/P3 comme filtre visuel exploratoire, pas comme prédiction.

    Rationale : le score v2 est plus bas que v1 d'environ 20–25 pts en moyenne
    (suppression cold_air/circularité/densité qui ajoutaient 20–33 pts non-discriminants).
    Les seuils ont été abaissés en proportion pour maintenir un rappel P1+P2 cohérent
    avec les résultats de validation IKarre. La limite physique irréductible (~10 % de
    cavités sans empreinte morphologique) reste inchangée.
    """
    if score >= 55:
        return "rouge"
    if score >= 35:
        return "orange"
    if score >= 25:
        return "jaune"
    return "gris"


def _compute_lisere_bonus(
    centroids,
    n_voisines_min: int = 3,
    rayon_m: float = 100.0,
    std_max_deg: float = 20.0,
    bonus_pts: float = 10.0,
) -> np.ndarray:
    """
    Bonus liseré : détecte les dolines alignées directionnellement.

    Dans le karst de contact (Barrois), les dolines se regroupent en liserés
    sinueux qui suivent la trace du contact lithostratigraphique.  Une doline
    appartenant à un tel alignement (≥ n_voisines_min voisines dans rayon_m,
    écart-type circulaire d'azimut ≤ std_max_deg) reçoit le bonus.

    Critères v2 (ScoringReview 2026) : rayon réduit à 100 m (200 m trop permissif),
    std_max_deg réduit à 20° (30° capturait des groupements non-directionnels).

    Statistiques circulaires sur directions mod 180°
    (un liseré a une direction, pas un sens) — doublement d'angle classique.
    """
    n = len(centroids)
    bonuses = np.zeros(n)
    if n < n_voisines_min + 1:
        return bonuses

    xs = np.array([c.x for c in centroids])
    ys = np.array([c.y for c in centroids])

    for i in range(n):
        dx = xs - xs[i]
        dy = ys - ys[i]
        dists = np.sqrt(dx ** 2 + dy ** 2)
        mask = (dists > 0) & (dists <= rayon_m)
        if mask.sum() < n_voisines_min:
            continue

        # Azimut géographique (N=0°, E=90°) mod 180° → direction sans sens
        azimuths = np.degrees(np.arctan2(dx[mask], dy[mask])) % 180.0

        # Doublement → statistique circulaire standard (von Mises)
        angles_rad = np.radians(azimuths * 2.0)
        R = float(np.abs(np.mean(np.exp(1j * angles_rad))))

        # Écart-type circulaire (en degrés) pour la direction originale
        R = min(R, 1.0 - 1e-9)
        std_deg = np.degrees(np.sqrt(-2.0 * np.log(R))) / 2.0

        if std_deg <= std_max_deg:
            bonuses[i] = bonus_pts

    return bonuses


def compute_scores(dolines: gpd.GeoDataFrame,
                   geology: gpd.GeoDataFrame,
                   topo=None,
                   config: dict | None = None) -> gpd.GeoDataFrame:
    """Calcule le score de prospection spéléologique de chaque doline (v2.0).

    Score = **Bloc A uniquement** (morphologie intrinsèque + géologie).
    La topographie souterraine (``topo``) est conservée uniquement comme couche
    informative — elle n'intervient plus dans le score depuis la validation IKarre
    (Ancerville 2026 : Bloc B n'a modifié aucune priorité sur les 35 cavités connues).

    Composantes Bloc A (v2.0) :
    ┌──────────────────────┬──────┬──────────────────────────────────────────────┐
    │ Composante           │ Max  │ Remarque                                      │
    ├──────────────────────┼──────┼──────────────────────────────────────────────┤
    │ surface              │  10  │ inchangée                                     │
    │ profondeur           │  30  │ continu au-delà de 8 m (+0.4 pt/m)           │
    │ ratio P/√S           │   8  │ réduit (redondance partielle avec profondeur) │
    │ pente_bord           │  20  │ inchangée                                     │
    │ lisere               │  10  │ v2 : en score (rayon 100 m, std 20°)         │
    │ absorption           │  18  │ réduit (était 25)                             │
    │ contact_geologique   │  25  │ + facteur karstifiabilité par CODE_LEG        │
    │ tpi_500m             │   8  │ NOUVEAU — doline sommitale vs fond de vallon  │
    ├──────────────────────┼──────┼──────────────────────────────────────────────┤
    │ TOTAL MAX THÉORIQUE  │ 129  │ clipé à 100                                  │
    └──────────────────────┴──────┴──────────────────────────────────────────────┘

    Colonnes calculées mais **hors score** (informatives) :
    - cold_air_index  : redondant avec profondeur et ratio P/√S (ScoringReview 2026)
    - circularite     : pénalise les dolines structurales allongées du Barrois
    - comp_densite_500m : non-discriminant en Barrois dense (> 50 voisines partout)

    Validation IKarre (5 communes, 300+ cavités, 2026, rayon 50 m) :
      - 3 communes de calibration : rappel P1+P2 28–54 %, z 2,9–4,7.
      - 2 communes HORS-ÉCHANTILLON : z ≤ 1,1 (Lisle même < 0) → le score à
        poids manuels ne bat PAS le hasard sur du terrain neuf (AUC 0,56).
      - Pondération APPRISE (leave-one-commune-out) : AUC 0,72 par domaine
        géologique → l'idée tient, les poids manuels sont à refaire.
      NB : le diagnostic logistique contredit les commentaires ci-dessus sur
      cold_air_index/circularité (jugés non-discriminants à tort : circularité
      ressort utile). cf. prototypes/feature_weights.py et loco_cv.py.

    Args:
        dolines  : GeoDataFrame des dépressions détectées (EPSG:2154).
                   Colonnes attendues : surface_m2, profondeur_m, altitude_m,
                   bassin_versant_m2, cold_air_index, pente_max_bord.
        geology  : GeoDataFrame des formations karstiques (EPSG:2154).
                   GeoDataFrame vide → score géologie = 0 pour toutes les dolines.
                   Colonne CODE_LEG utilisée pour le facteur karstifiabilité si présente.
        topo     : TopoNetwork optionnel — uniquement pour les colonnes informatives
                   ``comp_dist_reseau_m`` et ``comp_in_couloir``. N'affecte pas le score.
        config   : dict issu de ``load_config()``. None → ``default_scoring.json``.

    Returns:
        GeoDataFrame dolines enrichi des colonnes score_morpho, score,
        priorite, et toutes les colonnes comp_*.
    """
    if config is None:
        default = Path(__file__).parent.parent / "config" / "default_scoring.json"
        config = load_config(default)

    if dolines.empty:
        result = dolines.copy()
        for col in ("score_morpho", "score", "ratio_ps", "tpi_500m"):
            result[col] = []
        result["priorite"] = []
        return result

    a = config["bloc_a"]

    centroids = dolines.geometry.centroid
    result = dolines.copy()

    # ------------------------------------------------------------------ #
    # BLOC A — score morphologique (v2.0)
    # ------------------------------------------------------------------ #

    # ── Surface — poids 10 pts ────────────────────────────────────────────
    surf = dolines["surface_m2"].values
    surf_seuils = a["surface"].get("seuils", [50, 300, 1500])
    surf_pts    = a["surface"].get("points", [2, 5, 8, 10])
    surf_score = np.select(
        [surf < surf_seuils[0],
         surf < surf_seuils[1],
         surf < surf_seuils[2]],
        surf_pts[:3],
        default=surf_pts[3],
    ).astype(float)

    # ── Profondeur — poids 30 pts, continu au-delà de 8 m ────────────────
    # Barème par paliers jusqu'à 8 m, puis progression linéaire (+0.4 pt/m)
    # plafonnée à continu_max (30 pts). Ce mode continu évite la discontinuité
    # artificielle qui faisait stagner les gouffres de 8–20 m au même score.
    prof = dolines["profondeur_m"].values
    prof_seuils    = a["profondeur"].get("seuils", [0.3, 1.0, 3.0, 8.0])
    prof_pts       = a["profondeur"].get("points", [1, 6, 13, 22])
    continu_pente  = a["profondeur"].get("continu_pente", 0.4)   # pts par mètre > 8 m
    continu_max    = a["profondeur"].get("continu_max",   30)    # plafond absolu

    # Valeur de base depuis le barème (paliers jusqu'à 8 m)
    prof_base = np.select(
        [prof < prof_seuils[0],
         prof < prof_seuils[1],
         prof < prof_seuils[2],
         prof < prof_seuils[3]],
        prof_pts[:4],
        default=prof_pts[3],  # = 22 pts pour prof ≥ 8 m avant correction continue
    ).astype(float)

    # Correction continue pour prof > 8 m (dernier palier)
    seuil_continu = prof_seuils[3]   # 8.0 m par défaut
    prof_score = np.where(
        prof > seuil_continu,
        np.minimum(
            prof_base + (prof - seuil_continu) * continu_pente,
            float(continu_max),
        ),
        prof_base,
    )

    # ── Ratio P/√S — poids 8 pts (réduit depuis 12, v2) ─────────────────
    # P/√S est partiellement redondant avec profondeur et cold_air_index
    # (ScoringReview 2026) — on le conserve mais à poids réduit.
    ratio_ps = np.where(surf > 0, prof / np.sqrt(surf), 0.0)
    ratio_seuils = a.get("ratio_ps", {}).get("seuils", [0.1, 0.2, 0.4])
    ratio_pts    = a.get("ratio_ps", {}).get("points", [0, 3, 6, 8])
    ratio_score = np.select(
        [ratio_ps < ratio_seuils[0],
         ratio_ps < ratio_seuils[1],
         ratio_ps < ratio_seuils[2]],
        ratio_pts[:3],
        default=ratio_pts[3],
    ).astype(float)

    # ── Cold air index — INFORMATIF UNIQUEMENT (poids 0 en v2) ───────────
    # Redondant avec profondeur et P/√S (ScoringReview 2026). Calculé et
    # stocké dans le GPKG pour analyse, mais exclu de la somme morpho.
    cai_cfg = a.get("cold_air_index", {})
    if cai_cfg and "cold_air_index" in dolines.columns:
        cai = dolines["cold_air_index"].fillna(0).values.astype(float)
        cai_seuils = cai_cfg.get("seuils", [0.3, 0.5, 0.7])
        cai_pts    = cai_cfg.get("points", [0, 3, 6, 10])
        # cai_score calculé pour référence mais NON ajouté à morpho
        _cai_score_info = np.select(
            [cai < cai_seuils[0],
             cai < cai_seuils[1],
             cai < cai_seuils[2]],
            cai_pts[:3],
            default=cai_pts[3],
        ).astype(float)
    else:
        cai = np.zeros(len(dolines))
        _cai_score_info = np.zeros(len(dolines))

    # ── Circularité — INFORMATIVE UNIQUEMENT (poids 0 en v2) ─────────────
    # 4π·S/P² : pénalise les dolines structurales allongées du Barrois
    # (ScoringReview 2026 : contre-productive pour ce type de karst).
    # Calculée et stockée pour analyse, mais exclue de la somme morpho.
    circ_cfg = a.get("circularite", {})
    perimeters = dolines.geometry.length.values
    safe_perim = np.where(perimeters > 0, perimeters, 1.0)
    circ = 4 * np.pi * surf / (safe_perim ** 2)
    if circ_cfg:
        circ_seuils = circ_cfg.get("seuils", [0.4, 0.6, 0.8])
        circ_pts    = circ_cfg.get("points", [0, 3, 6, 8])
        # _circ_score_info calculé pour référence mais NON ajouté à morpho
        _circ_score_info = np.select(
            [circ < circ_seuils[0],
             circ < circ_seuils[1],
             circ < circ_seuils[2]],
            circ_pts[:3],
            default=circ_pts[3],
        ).astype(float)
    else:
        _circ_score_info = np.zeros(len(dolines))

    # ── Pente bord — poids 20 pts ─────────────────────────────────────────
    # pente_max_bord calculée en p90 sur anneau 5 m (cold_air.py v2).
    pente_seuils = a.get("pente_bord", {}).get("seuils", [20.0, 45.0, 70.0])
    pente_pts    = a.get("pente_bord", {}).get("points", [0, 5, 12, 20])
    if "pente_max_bord" in dolines.columns:
        pente = dolines["pente_max_bord"].fillna(0).values.astype(float)
    else:
        pente = np.zeros(len(dolines))
    pente_score = np.select(
        [pente < pente_seuils[0],
         pente < pente_seuils[1],
         pente < pente_seuils[2]],
        pente_pts[:3],
        default=pente_pts[3],
    ).astype(float)

    # ── Liseré — poids 10 pts, EN SCORE depuis v2 ─────────────────────────
    # Critères resserrés v2 : rayon 100 m (était 200 m) et std 20° (était 30°).
    # En_score=True active la prise en compte dans la somme morpho. Cela récompense
    # les dolines alignées le long du contact lithostratigraphique (Barrois).
    lisere_cfg     = a.get("lisere", {})
    lisere_bonus   = lisere_cfg.get("bonus", 10)
    lisere_rayon   = lisere_cfg.get("rayon_m", 100.0)
    lisere_n_min   = lisere_cfg.get("n_min", 3)
    lisere_std_max = lisere_cfg.get("std_max_deg", 20.0)
    lisere_en_score = lisere_cfg.get("en_score", False)

    lisere_score = _compute_lisere_bonus(
        centroids,
        n_voisines_min=lisere_n_min,
        rayon_m=lisere_rayon,
        std_max_deg=lisere_std_max,
        bonus_pts=lisere_bonus,
    )
    # Contribution au score uniquement si en_score=True dans la config
    lisere_score_pts = lisere_score if lisere_en_score else np.zeros(len(dolines))

    # ── Absorption — poids 18 pts (réduit depuis 25, v2) ─────────────────
    # Bassin versant amont D8 en m². Proxy hydraulique d'infiltration.
    absorb_cfg    = a.get("absorption", {})
    absorb_seuils = absorb_cfg.get("seuils", [1_000, 5_000, 20_000])
    absorb_pts    = absorb_cfg.get("points", [0, 6, 12, 18])

    if "bassin_versant_m2" in dolines.columns:
        bv = dolines["bassin_versant_m2"].fillna(0).values.astype(float)
        absorb_score = np.select(
            [bv < absorb_seuils[0],
             bv < absorb_seuils[1],
             bv < absorb_seuils[2]],
            absorb_pts[:3],
            default=absorb_pts[3],
        ).astype(float)
    else:
        # Fallback si colonne absente (ancien GPKG sans flow_acc)
        absorb_score = np.zeros(len(dolines))

    # ── Densité 500 m — INFORMATIVE UNIQUEMENT (poids 0 en v2) ───────────
    # Non-discriminante en Barrois dense : > 50 voisines = 15 pts pour tout
    # le monde, donc n'ajoute aucune information utile (ScoringReview 2026).
    # On conserve le calcul car comp_densite_500m est exporté dans le GPKG
    # et utilisé par l'analyse MLL pour qualifier la densité morphologique.
    centroid_gdf = gpd.GeoDataFrame(geometry=centroids, crs=dolines.crs)
    sindex = centroid_gdf.sindex
    density_counts = np.zeros(len(dolines), dtype=int)
    altitudes = dolines["altitude_m"].values.astype(float) if "altitude_m" in dolines.columns else np.full(len(dolines), np.nan)
    tpi_vals = np.zeros(len(dolines))

    for i, c in enumerate(centroids):
        bbox = (c.x - 500, c.y - 500, c.x + 500, c.y + 500)
        candidates = list(sindex.intersection(bbox))
        close_mask = centroids.iloc[candidates].distance(c) < 500
        close_indices = [candidates[j] for j, ok in enumerate(close_mask) if ok and candidates[j] != i]
        density_counts[i] = len(close_indices)

        # TPI : altitude de la doline vs moyenne des voisines dans 500 m
        # TPI > 0 = doline sommitale (absorption directe, favorable)
        # TPI < -20 = fond de vallon (moins discriminant en karst de contact)
        if close_indices and np.isfinite(altitudes[i]):
            neighbor_alts = altitudes[close_indices]
            valid_alts = neighbor_alts[np.isfinite(neighbor_alts)]
            if valid_alts.size > 0:
                tpi_vals[i] = altitudes[i] - float(np.mean(valid_alts))
            # Si tous les voisins ont NaN altitude → TPI = 0 (neutre)

    # Barème TPI : [-∞, -20) → 0 pts, [-20, 0) → 3, [0, 20) → 5, [20, +∞) → 8
    tpi_cfg    = a.get("tpi_500m", {})
    tpi_seuils = tpi_cfg.get("seuils", [-20.0, 0.0, 20.0])
    tpi_pts    = tpi_cfg.get("points", [0, 3, 5, 8])
    tpi_score = np.select(
        [tpi_vals < tpi_seuils[0],
         tpi_vals < tpi_seuils[1],
         tpi_vals < tpi_seuils[2]],
        tpi_pts[:3],
        default=tpi_pts[3],
    ).astype(float)

    # ── Contact géologique — poids 25 pts + facteur karstifiabilité ───────
    # Gradient exponentiel depuis le bord du polygone karstifiable (decay 250 m).
    # v2 : facteur multiplicatif par CODE_LEG (karstifiabilite dans la config).
    #      1.0 = calcaire tithonien/oxfordien optimal, 0.3 = craie peu karstifiée.
    #      Permet de différencier les calcaires sans modifier la géométrie BD Charm-50.
    geo_score = np.zeros(len(dolines))
    geo_dist  = np.full(len(dolines), np.nan)   # distance au bord (informatif)
    if not geology.empty:
        geo_cfg   = a["contact_geologique"]
        full_pts  = geo_cfg.get("poids", 25)
        decay_m   = geo_cfg.get("gradient_decay_m", None)  # None → binaire (compat. tests)
        karst_factors = geo_cfg.get("karstifiabilite", {})
        default_factor = karst_factors.get("default", 1.0)

        geo_sindex = geology.sindex
        # Colonne CODE_LEG disponible dans BD Charm-50 pour facteur karstifiabilité
        has_code_leg = "CODE_LEG" in geology.columns

        for i, centroid in enumerate(centroids):
            candidates = list(geo_sindex.intersection(centroid.bounds))
            containing = [j for j in candidates
                          if geology.geometry.iloc[j].contains(centroid)]
            if containing:
                # Sélectionner le polygone contenant avec la distance bord minimale
                # (dans le cas de polygones imbriqués ou superposés)
                dist_boundary = min(
                    geology.geometry.iloc[j].boundary.distance(centroid)
                    for j in containing
                )
                geo_dist[i] = round(dist_boundary, 0)

                # Facteur karstifiabilité : code lithologique → multiplicateur [0-1]
                # Par défaut 1.0 si CODE_LEG absent ou non trouvé dans la config
                kfactor = default_factor
                if has_code_leg and containing:
                    # Utiliser le polygone avec la plus grande intersection (premier)
                    code = geology.iloc[containing[0]].get("CODE_LEG", "")
                    if code:
                        kfactor = karst_factors.get(str(code).lower(), default_factor)

                if decay_m:
                    raw_score = full_pts * float(np.exp(-dist_boundary / decay_m))
                else:
                    raw_score = full_pts   # compat. tests sans gradient_decay_m

                geo_score[i] = raw_score * kfactor

    # ── Morpho total — somme clippée à 100 ───────────────────────────────
    # Composantes v2 incluses dans le score :
    #   surf10 + prof30 + ratio8 + pente20 + liseré10 + absorb18 + geo25 + tpi8 = 129 max
    # Composantes exclues (informatives) : cold_air_index, circularite, densite_500m
    morpho = np.clip(
        surf_score + prof_score + ratio_score +
        pente_score + lisere_score_pts +
        absorb_score + geo_score + tpi_score,
        0, 100,
    )

    # ------------------------------------------------------------------ #
    # Topo — colonnes informatives uniquement (n'influe pas sur le score)
    # ------------------------------------------------------------------ #
    has_topo = topo is not None and not topo.passages.empty
    dist_reseau = np.full(len(dolines), np.nan)
    in_couloir  = np.zeros(len(dolines), dtype=bool)

    if has_topo:
        from shapely.ops import unary_union

        corridor_geom = unary_union(topo.passages.geometry).buffer(500)
        topo_sindex   = topo.passages.sindex

        for i, c in enumerate(centroids):
            candidates = list(topo_sindex.intersection(
                (c.x - 5000, c.y - 5000, c.x + 5000, c.y + 5000)
            ))
            if candidates:
                dist = topo.passages.geometry.iloc[candidates].distance(c).min()
            else:
                dist = topo.passages.geometry.distance(c).min()
            dist_reseau[i] = round(dist, 0)

            if c.within(corridor_geom):
                in_couloir[i] = True

    # ------------------------------------------------------------------ #
    # Score final = Bloc A (morphologie) — clippé à 100
    # ------------------------------------------------------------------ #
    final = np.round(morpho, 1)

    result["score_morpho"]  = np.round(morpho, 1)
    result["ratio_ps"]      = np.round(ratio_ps, 3)
    result["pente_max_bord"] = np.round(pente, 1)
    result["lisere"]        = lisere_score.astype(bool)   # flag booléen (indépendant de en_score)
    result["tpi_500m"]      = np.round(tpi_vals, 1)       # TPI brut en mètres
    result["score"]         = final
    result["priorite"]      = [score_to_priority(s) for s in final]

    # ── Composantes informatives — pour analyse MLL et GPKG ──────────────
    result["circularite"]        = np.round(circ, 3)
    _bv = dolines["bassin_versant_m2"].fillna(0).values if "bassin_versant_m2" in dolines.columns else np.zeros(len(dolines))
    _seuil_comp = a.get("absorption", {}).get("seuils", [1_000, 5_000, 20_000])[1]
    result["comp_absorption"]      = _bv >= _seuil_comp
    result["comp_geologie"]        = geo_score > 0
    result["comp_geologie_dist_m"] = geo_dist
    result["comp_dist_reseau_m"]   = dist_reseau   # informatif — distance au passage topo le plus proche
    result["comp_in_couloir"]      = in_couloir     # informatif — doline dans un couloir de galeries
    result["comp_densite_500m"]    = density_counts.astype(int)
    return result


def compute_cavites_connues_proximity(
    dolines: gpd.GeoDataFrame,
    cavites_connues: gpd.GeoDataFrame,
    radius_m: float = 20.0,
) -> gpd.GeoDataFrame:
    """Enrichit les dolines avec l'information de proximité aux cavités connues.

    Pour chaque doline, identifie la cavité connue la plus proche.
    Si elle est dans le rayon, la doline est flaggée comme doublon potentiel.
    Ce flag est purement informatif — il ne modifie pas le score.

    Préférence inventaire : si la couche porte une colonne ``_source`` (tag
    "inventaire" vs "georisques"), et qu'une cavité de l'inventaire utilisateur
    est dans le rayon, c'est elle qui est liée (nom/réf fiables), même si une
    cavité Géorisques « anonyme » est légèrement plus proche.

    Le rayon par défaut de 20 m correspond à la marge d'erreur GPS + imprécision
    de pointé. Dans un karst sous couverture (Barrois), deux dolines à 25 m peuvent
    alimenter des conduits distincts — 20 m est plus conservateur que 50 m.

    Colonnes ajoutées :
    - cavite_connue_proche (bool)  : True si une cavité connue est dans radius_m
    - cavite_distance_m (float)    : distance en mètres à la cavité la plus proche
                                     (toujours renseignée — utile : loin de tout
                                     connu = territoire vierge)
    - cavite_nom (str)             : nom de la cavité la plus proche, UNIQUEMENT
                                     si elle est dans radius_m (sinon vide, pour
                                     ne pas « rattacher » une cavité lointaine à
                                     la fiche d'une doline)
    - cavite_type (str)            : type de la cavité proche (sinon vide)
    - cavite_ref (str)             : référence de la cavité proche (sinon vide)

    Args:
        dolines          : GeoDataFrame des dolines scorées (EPSG:2154)
        cavites_connues  : GeoDataFrame des cavités connues (tout CRS → reprojeté)
        radius_m         : rayon de déduplication en mètres (défaut : 20 m)

    Returns:
        GeoDataFrame dolines enrichi des colonnes cavite_*
    """
    dolines = dolines.copy()

    # Colonnes par défaut si la fonction est appelée sans cavités
    dolines["cavite_connue_proche"] = False
    dolines["cavite_nom"]           = ""
    dolines["cavite_distance_m"]    = np.nan
    dolines["cavite_type"]          = ""
    dolines["cavite_ref"]           = ""

    if cavites_connues is None or cavites_connues.empty:
        return dolines

    # Reprojection si nécessaire
    if cavites_connues.crs is None:
        cavites_connues = cavites_connues.set_crs("EPSG:2154")
    elif cavites_connues.crs.to_epsg() != 2154:
        cavites_connues = cavites_connues.to_crs("EPSG:2154")

    # Centroïdes des dolines pour le calcul de distance
    doline_centroids = dolines.geometry.centroid

    # Masque des cavités issues de l'inventaire utilisateur (prioritaires sur
    # Géorisques pour l'étiquetage). Absent si la couche n'est pas taguée.
    inv_mask = (cavites_connues["_source"] == "inventaire") \
        if "_source" in cavites_connues.columns else None

    # Pour chaque doline : distance à la cavité la plus proche
    for i, centroid in enumerate(doline_centroids):
        distances = cavites_connues.geometry.distance(centroid)
        idx_min   = distances.idxmin()
        dist_min  = distances[idx_min]
        proche    = dist_min <= radius_m

        dolines.at[dolines.index[i], "cavite_connue_proche"] = proche

        # Nom/type/réf : seulement si une cavité connue est réellement proche.
        # Sinon on ne rattache pas une cavité parfois à >1 km à la fiche (sans
        # quoi toutes les dolines « référenceraient » la plus proche).
        if proche:
            # Préférence inventaire : si une cavité de l'inventaire est dans le
            # rayon, on la lie (nom/réf fiables) plutôt qu'une cavité Géorisques
            # « anonyme » même légèrement plus proche. Sinon, la plus proche.
            idx_link, dist_link = idx_min, dist_min
            if inv_mask is not None:
                inv_within = distances[(distances <= radius_m) & inv_mask]
                if not inv_within.empty:
                    idx_link = inv_within.idxmin()
                    dist_link = inv_within[idx_link]
            row = cavites_connues.loc[idx_link]
            dolines.at[dolines.index[i], "cavite_distance_m"] = round(float(dist_link), 1)
            dolines.at[dolines.index[i], "cavite_nom"]  = str(row.get("name",  "") or "")
            dolines.at[dolines.index[i], "cavite_type"] = str(row.get("type",  "") or "")
            dolines.at[dolines.index[i], "cavite_ref"]  = str(row.get("reference", "") or "")
        else:
            # Pas de cavité proche : on garde quand même la distance au connu le
            # plus proche (loin de tout = territoire vierge).
            dolines.at[dolines.index[i], "cavite_distance_m"] = round(float(dist_min), 1)

    return dolines
