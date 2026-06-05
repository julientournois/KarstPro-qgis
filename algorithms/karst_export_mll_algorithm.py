# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterDefinition,
    QgsProcessingContext,
    QgsProcessingFeedback,
)
import math
from pathlib import Path


class KarstExportMllAlgorithm(QgsProcessingAlgorithm):
    GPKG = "GPKG"
    SECTEUR = "SECTEUR"
    OUTPUT_DIR = "OUTPUT_DIR"
    CONTEXT = "CONTEXT"
    INVENTORY_GPKG = "INVENTORY_GPKG"
    TRACAGES_GPKG = "TRACAGES_GPKG"

    def name(self):
        return "karst_export_mll"

    def displayName(self):
        return "KarstPro — Exporter pour analyse MLL"

    def group(self):
        return "KarstPro"

    def groupId(self):
        return "karstpro"

    def createInstance(self):
        return KarstExportMllAlgorithm()

    def helpUrl(self):
        from karstpro.core.log_feedback import doc_url
        return doc_url()

    def icon(self):
        from karstpro.icons import karst_icon
        ic = karst_icon()
        return ic if ic is not None else super().icon()

    def shortHelpString(self):
        return (
            "Génère un rapport Markdown et un prompt prêt à coller dans MLL "
            "pour une analyse spéléologique approfondie du secteur.\n\n"
            "Si le champ « Direction du pendage » est laissé vide, il est estimé "
            "automatiquement depuis la couche géologie + le MNT (lidar_work/mnt.tif).\n\n"
            "Résultat dans le dossier de sortie :\n"
            "• mll_prompt_<secteur>_<date>.txt — prompt à coller dans MLL "
            "(rapport complet inclus)\n"
            "• cibles_<secteur>_<date>.gpx — waypoints GPS rouges + oranges\n\n"
            "MLL produit en retour :\n"
            "• Analyse priorisée + ordre de visite optimal\n"
            "• Export GPX ordonné\n"
            "• Export CSV pour QGIS\n"
            "• Script Python python-docx pour générer le rapport DOCX complet"
        )

    PENDAGE      = "PENDAGE"
    ZONES_EXCLUES = "ZONES_EXCLUES"

    def _add_advanced(self, param):
        """Place le paramètre dans la section repliable « Paramètres avancés »."""
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

    def initAlgorithm(self, config=None):
        # ── Paramètres requis (toujours visibles) ──────────────────────────
        self.addParameter(QgsProcessingParameterFile(
            self.GPKG,
            "GeoPackage KarstPro (.gpkg)",
            extension="gpkg",
        ))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.OUTPUT_DIR,
            "Dossier de sortie (optionnel — par défaut, dossier du GeoPackage)",
            optional=True, createByDefault=False,
        ))

        # GeoPackages inventaire (cavités connues / traçages) — désormais
        # référencés et non copiés dans le package : le MLL les relit ici.
        self._add_advanced(QgsProcessingParameterFile(
            self.INVENTORY_GPKG,
            "GeoPackage inventaire cavités (.gpkg — cavités connues pour le MLL)",
            optional=True, extension="gpkg",
        ))
        self._add_advanced(QgsProcessingParameterFile(
            self.TRACAGES_GPKG,
            "GeoPackage traçages (.gpkg — traçages pour le MLL)",
            optional=True, extension="gpkg",
        ))

        # ── Paramètres optionnels (section « avancés », repliée par défaut) ─
        self._add_advanced(QgsProcessingParameterString(
            self.SECTEUR,
            "Nom du secteur (auto-détecté si vide)",
            defaultValue="",
            optional=True,
        ))
        self._add_advanced(QgsProcessingParameterString(
            self.CONTEXT,
            "Contexte terrain (géologie locale, historique explorations…)",
            defaultValue="",
            optional=True,
            multiLine=True,
        ))
        self._add_advanced(QgsProcessingParameterString(
            self.PENDAGE,
            "Direction du pendage / sens de drainage "
            "(laisser vide = estimation auto depuis géologie + MNT)",
            defaultValue="",
            optional=True,
        ))
        self._add_advanced(QgsProcessingParameterString(
            self.ZONES_EXCLUES,
            "Zones à exclure de la prospection (ex: quadrant sud — falaises, propriété privée…)",
            defaultValue="",
            optional=True,
        ))

    def processAlgorithm(self, parameters, context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        import traceback

        try:
            return self._run(parameters, context, feedback)
        except Exception:
            feedback.reportError(
                f"ERREUR dans KarstExportMLL :\n{traceback.format_exc()}",
                fatalError=True,
            )
            raise

    def _read_dolines_sqlite(self, gpkg_path: Path, feedback) -> list:
        """Lit la couche dolines via sqlite3 + shapely, sans passer par pyproj.

        pyogrio→pyproj→proj_create n'est pas thread-safe dans QGIS 4.0.2.
        On parse directement le WKB GPKG pour extraire le centroïde de chaque polygone.
        """
        import sqlite3
        import struct

        FLOAT64 = struct.Struct("<d")  # little-endian double

        def _centroid_from_gpkg_geom(blob):
            """Extrait le centroïde (x, y) depuis un blob de géométrie GPKG.

            Format GPKG : 2 octets magic 'GP' + 1 version + 1 flags + 4 SRS_ID
            + envelope optionnelle + WKB ISO.

            Stratégie : si une envelope XY est présente (flag bits 1-3 = 1),
            on lit directement min/max XY (8 doubles = midpoint exact pour bbox).
            Sinon on parse le WKB avec shapely.
            """
            if not blob or len(blob) < 8:
                return None, None
            flags = blob[3]
            env_indicator = (flags >> 1) & 0x07

            # Tailles d'envelope : 0=none, 1=XY(32), 2=XYZ(48), 3=XYM(48), 4=XYZM(64)
            env_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
            env_size = env_sizes.get(env_indicator, 0)

            wkb_offset = 8 + env_size

            if env_indicator >= 1:
                # Utiliser l'envelope : minX, maxX, minY, maxY (doubles LE à partir de byte 8)
                try:
                    minX = FLOAT64.unpack_from(blob, 8)[0]
                    maxX = FLOAT64.unpack_from(blob, 16)[0]
                    minY = FLOAT64.unpack_from(blob, 24)[0]
                    maxY = FLOAT64.unpack_from(blob, 32)[0]
                    return (minX + maxX) / 2.0, (minY + maxY) / 2.0
                except struct.error:
                    pass

            # Fallback : parser le WKB complet avec shapely
            try:
                from shapely import wkb as swkb
                geom = swkb.loads(bytes(blob[wkb_offset:]))
                c = geom.centroid
                return c.x, c.y
            except Exception:
                return None, None

        def _safe_float(val):
            if val is None:
                return None
            try:
                f = float(val)
                return None if math.isnan(f) else f
            except (TypeError, ValueError):
                return None

        con = sqlite3.connect(str(gpkg_path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Trouver le nom de la colonne géométrie
        try:
            cur.execute(
                "SELECT column_name FROM gpkg_geometry_columns WHERE table_name='dolines'"
            )
            row = cur.fetchone()
            geom_col = row[0] if row else "geom"
        except Exception:
            geom_col = "geom"

        # Trouver la table dolines (nom exact dans le GPKG)
        cur.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
        )
        available = [r[0] for r in cur.fetchall()]
        # Cherche "dolines" en priorité, puis toute table contenant "doline"
        dolines_table = None
        if "dolines" in available:
            dolines_table = "dolines"
        else:
            for t in available:
                if "doline" in t.lower():
                    dolines_table = t
                    break
        if dolines_table is None:
            con.close()
            raise ValueError(
                f"Aucune couche 'dolines' trouvée dans {gpkg_path.name}. "
                f"Couches disponibles : {available}. "
                f"Sélectionnez le GeoPackage généré par 'Préparer une sortie'."
            )

        # Lister toutes les colonnes attributaires
        cur.execute(f'SELECT * FROM "{dolines_table}" LIMIT 0')
        all_cols = [d[0] for d in cur.description]
        attr_cols = [c for c in all_cols if c != geom_col]

        col_sql = ", ".join(f'"{c}"' for c in attr_cols) + f', "{geom_col}"'
        cur.execute(f'SELECT {col_sql} FROM "{dolines_table}"')

        rows_out = []
        for row in cur.fetchall():
            d = {}
            for c in attr_cols:
                d[c] = row[c]

            # ID = fid GPKG (1-based). La preparation nomme desormais les cibles
            # "doline_{fid}" (cf. qfield.write_cibles + reset_index a la prep),
            # donc l'export utilise le fid tel quel : "doline_N" du rapport ==
            # "doline_N" sur la carte == fid N dans la table attributaire.
            if d.get("fid") is not None:
                try:
                    d["fid"] = int(d["fid"])
                except (TypeError, ValueError):
                    pass

            x, y = _centroid_from_gpkg_geom(row[geom_col])
            d["x_l93"] = round(x, 0) if x is not None else None
            d["y_l93"] = round(y, 0) if y is not None else None

            # Normalisation des champs numériques
            for field, decimals in [
                ("surface_m2", 1), ("profondeur_m", 2),
                ("score_morpho", 1), ("score", 1),
                ("ratio_ps", 3), ("pente_max_bord", 1), ("cold_air_index", 3),
                ("comp_geologie_dist_m", 0), ("cavite_distance_m", 0),
            ]:
                if field in d and d[field] is not None:
                    f = _safe_float(d[field])
                    d[field] = round(f, decimals) if f is not None else None

            for field in ("lisere", "cavite_connue_proche"):
                if field in d:
                    d[field] = bool(d[field])

            rows_out.append(d)

        con.close()
        return sorted(rows_out, key=lambda r: (r.get("score") or 0), reverse=True)

    def _read_tracages_gpkg(self, cur, feedback, table: str = "tracages") -> list:
        """Lit la couche traçages (``table``) du gpkg (LineString) via sqlite.

        Renvoie une liste de dicts : attributs (point_injection, point_sortie,
        colorant, resultat, temps_transit, distance_m…) + coordonnées L93 des
        extrémités (x_inj/y_inj = 1er sommet, x_res/y_res = dernier sommet).
        On suppose le gpkg inventaire en EPSG:2154 (contrat de schéma) : les
        coordonnées sont lues telles quelles, sans pyproj (thread-safe).
        """
        from shapely import wkb as swkb

        # Nom de la colonne géométrie
        try:
            cur.execute(
                "SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?",
                (table,),
            )
            r = cur.fetchone()
            geom_col = r[0] if r else "geom"
        except Exception:
            geom_col = "geom"

        # Attributs disponibles
        cur.execute(f'PRAGMA table_info("{table}")')
        cols = [c[1] for c in cur.fetchall()]
        wanted = [c for c in (
            "point_injection", "point_sortie", "colorant", "resultat",
            "date_injection", "date_detection", "temps_transit",
            "distance_m", "operateurs") if c in cols]
        attr_sql = ", ".join([geom_col] + wanted)

        def _endpoints(blob):
            """Extrait (x_inj,y_inj,x_res,y_res) en L93 depuis un blob GPKG."""
            if not blob or len(blob) < 8:
                return None
            flags = blob[3]
            env_indicator = (flags >> 1) & 0x07
            env_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
            wkb_offset = 8 + env_sizes.get(env_indicator, 0)
            try:
                geom = swkb.loads(bytes(blob[wkb_offset:]))
                coords = list(geom.coords) if geom.geom_type == "LineString" \
                    else list(geom.geoms[0].coords)
                if len(coords) < 2:
                    return None
                (xi, yi), (xr, yr) = coords[0][:2], coords[-1][:2]
                return round(xi, 0), round(yi, 0), round(xr, 0), round(yr, 0)
            except Exception:
                return None

        rows = []
        for row in cur.execute(f'SELECT {attr_sql} FROM "{table}"'):
            ep = _endpoints(row[0])
            if ep is None:
                continue
            d = {wanted[i]: row[i + 1] for i in range(len(wanted))}
            d.update({"x_inj": ep[0], "y_inj": ep[1],
                      "x_res": ep[2], "y_res": ep[3]})
            rows.append(d)
        feedback.pushInfo(f"  {len(rows)} traçage(s) chargé(s) depuis le gpkg.")
        return rows

    def _read_external_tracages(self, gpkg_path, feedback) -> list:
        """Lit les traçages depuis un gpkg externe (couche détectée par schéma)."""
        import sqlite3
        from karstpro.core.sync import find_tracages_layer
        table = find_tracages_layer(gpkg_path)
        if not table:
            feedback.pushWarning(
                f"Aucune couche traçages valide dans {gpkg_path.name}.")
            return []
        con = sqlite3.connect(str(gpkg_path))
        try:
            return self._read_tracages_gpkg(con.cursor(), feedback, table=table)
        except Exception as e:
            feedback.pushWarning(f"Traçages externes ignorés : {e}")
            return []
        finally:
            con.close()

    def _read_external_cavites_connues(self, gpkg_path, feedback) -> list:
        """Lit les cavités connues depuis un gpkg inventaire externe."""
        import sqlite3
        from karstpro.core.sync import find_inventory_layer
        table = find_inventory_layer(gpkg_path)
        if not table:
            feedback.pushWarning(
                f"Aucune couche inventaire valide dans {gpkg_path.name}.")
            return []
        con = sqlite3.connect(str(gpkg_path))
        try:
            cur = con.cursor()
            avail = {c[1] for c in cur.execute(f'PRAGMA table_info("{table}")')}
            cols = [c for c in ("name", "type", "date_disc", "date_expl",
                                "explorers", "comment", "reference") if c in avail]
            if not cols:
                return []
            sql = f'SELECT {", ".join(cols)} FROM "{table}" ORDER BY name'
            rows = [dict(zip(cols, r)) for r in cur.execute(sql)]
            feedback.pushInfo(
                f"  {len(rows)} cavité(s) connue(s) lue(s) depuis {gpkg_path.name}.")
            return rows
        except Exception as e:
            feedback.pushWarning(f"Cavités connues externes ignorées : {e}")
            return []
        finally:
            con.close()

    def _run(self, parameters, context: QgsProcessingContext,
             feedback: QgsProcessingFeedback):
        import sqlite3
        import json
        from datetime import date

        gpkg_path = Path(self.parameterAsFile(parameters, self.GPKG, context))
        secteur = self.parameterAsString(parameters, self.SECTEUR, context).strip()
        extra_context = self.parameterAsString(parameters, self.CONTEXT, context).strip()
        pendage = self.parameterAsString(parameters, self.PENDAGE, context).strip()
        zones_exclues = self.parameterAsString(parameters, self.ZONES_EXCLUES, context).strip()
        output_str = self.parameterAsString(parameters, self.OUTPUT_DIR, context)
        # Par défaut (champ vide) : le dossier du GeoPackage d'entrée.
        output_dir = Path(output_str) if output_str else gpkg_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        inv_gpkg_str = self.parameterAsFile(parameters, self.INVENTORY_GPKG, context)
        tr_gpkg_str = self.parameterAsFile(parameters, self.TRACAGES_GPKG, context)
        inventory_gpkg = Path(inv_gpkg_str) if inv_gpkg_str else None
        tracages_gpkg = Path(tr_gpkg_str) if tr_gpkg_str else None

        if not secteur:
            secteur = gpkg_path.stem

        # ── Dossier d'export + fichier log (capture tout le journal) ───────
        from datetime import datetime
        today = date.today()
        export_dir = output_dir / f"mll_export_{secteur}_{today}"
        export_dir.mkdir(parents=True, exist_ok=True)
        log_file = export_dir / f"mll_export_{secteur}_{today}.log"

        from karstpro.core.log_feedback import write_log_header, wrap_feedback
        write_log_header(log_file, f"KarstPro — Exporter pour analyse MLL ({secteur})", parameters)
        feedback = wrap_feedback(feedback, log_file)
        _t0 = datetime.now()

        feedback.pushInfo(f"Lecture de {gpkg_path.name}...")

        # Lecture via sqlite3 + shapely — évite pyproj qui n'est pas thread-safe
        # dans QGIS 4.0.2 (proj_create → DatabaseContext → access violation).
        dolines = self._read_dolines_sqlite(gpkg_path, feedback)

        # ── Pendage : auto-estimé si le champ est laissé vide ─────────────
        if not pendage:
            try:
                mnt_path = gpkg_path.parent / "lidar_work" / "mnt.tif"
                auto = _estimate_dip(gpkg_path, mnt_path)
                if auto:
                    pendage = auto["texte"]
                    feedback.pushInfo(
                        f"Pendage auto-estimé : {pendage} "
                        f"(contact {auto['contact']}, R²={auto['r2']:.2f})"
                    )
                else:
                    feedback.pushInfo(
                        "Pendage non estimé (pas de contact conformable exploitable "
                        "ou MNT absent) — champ laissé vide."
                    )
            except Exception as e:
                feedback.pushWarning(f"Estimation pendage échouée : {e}")

        # ── Flags découverte : profonde + hors réseau connu ──────────────
        # Heuristique : profondeur > 5m ET (pas de topo OU dist réseau > 500m)
        # Ces dolines ont un fort signal morphologique mais aucune association
        # au réseau connu — zones sous-explorées à prioriser pour la découverte.
        DECOUVERTE_PROF_MIN = 5.0
        DECOUVERTE_DIST_MIN = 500.0
        for d in dolines:
            prof      = d.get("profondeur_m") or 0.0
            dist_r    = d.get("comp_dist_reseau_m")
            loin_reseau = (dist_r is None or math.isnan(float(dist_r))
                           or float(dist_r) >= DECOUVERTE_DIST_MIN)
            d["decouverte"] = (prof >= DECOUVERTE_PROF_MIN and loin_reseau)

        cibles_decouverte = [d for d in dolines if d["decouverte"]]
        n_bonus_hors_couloir = len(cibles_decouverte)

        con = sqlite3.connect(gpkg_path)
        try:
            cur = con.cursor()

            feedback.pushInfo(f"  {len(dolines)} dolines chargées.")
            feedback.pushInfo(
                f"  {n_bonus_hors_couloir} cibles de découverte "
                f"(prof >= {DECOUVERTE_PROF_MIN}m, dist reseau > {DECOUVERTE_DIST_MIN}m ou sans topo)"
            )

            # ── Stats par priorité ────────────────────────────────────────────
            cur.execute("""
                SELECT priorite, COUNT(*),
                       ROUND(AVG(surface_m2),0), ROUND(MAX(surface_m2),0),
                       ROUND(AVG(profondeur_m),2), ROUND(MAX(profondeur_m),2),
                       ROUND(AVG(score),1), ROUND(MAX(score),1)
                FROM dolines GROUP BY priorite ORDER BY MAX(score) DESC
            """)
            stats = {}
            for row in cur.fetchall():
                stats[row[0]] = {
                    "n": row[1], "surf_moy": row[2], "surf_max": row[3],
                    "prof_moy": row[4], "prof_max": row[5],
                    "score_moy": row[6], "score_max": row[7],
                }

            # ── Cavités, topo ─────────────────────────────────────────────────
            def count_table(table):
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    return cur.fetchone()[0]
                except Exception:
                    return 0

            n_cavites = count_table("cavites")
            n_topo = count_table("topo_reseau")
            n_hydro = count_table("hydrologie")
            n_cav_georisques = count_table("cavites_georisques")

            from karstpro.core.sync import (
                find_inventory_layer, find_tracages_layer,
            )

            # Traçages : gpkg traçages externe si fourni, sinon la couche
            # traçages présente dans le gpkg courant (détectée par schéma).
            tracages_rows = []
            if tracages_gpkg is not None and tracages_gpkg.exists():
                tracages_rows = self._read_external_tracages(tracages_gpkg, feedback)
            else:
                tbl = find_tracages_layer(gpkg_path)
                if tbl:
                    try:
                        tracages_rows = self._read_tracages_gpkg(
                            cur, feedback, table=tbl)
                    except Exception as e:
                        feedback.pushWarning(f"Traçages (gpkg courant) ignorés : {e}")

            # Cavités connues : gpkg inventaire externe si fourni, sinon la couche
            # inventaire présente dans le gpkg courant (cavites_connues /
            # « Inventaire Cavités », hors tampon cavites).
            cavites_connues_rows = []
            if inventory_gpkg is not None and inventory_gpkg.exists():
                cavites_connues_rows = self._read_external_cavites_connues(
                    inventory_gpkg, feedback)
            elif find_inventory_layer(gpkg_path):
                cavites_connues_rows = self._read_external_cavites_connues(
                    gpkg_path, feedback)

            n_cav_connues = len(cavites_connues_rows)
            n_tracages = len(tracages_rows)

            # Charger les cavités Géorisques BRGM si présentes
            cavites_georisques_rows = []
            if n_cav_georisques > 0:
                try:
                    cur.execute("""
                        SELECT nom_cavite, type_cavite, identifiant,
                               date_validite, reperage_geographique
                        FROM cavites_georisques
                        ORDER BY nom_cavite
                    """)
                    cols_geo = ["nom_cavite", "type_cavite", "identifiant",
                                "date_validite", "reperage_geographique"]
                    for r in cur.fetchall():
                        cavites_georisques_rows.append(dict(zip(cols_geo, r)))
                except Exception:
                    pass

        finally:
            con.close()

        feedback.pushInfo(
            f"  {n_topo} segments topo, {n_cavites} cavites, "
            f"{n_cav_connues} cavité(s) connue(s), {n_tracages} traçage(s)."
        )
        feedback.setProgress(30)

        # ── Séparation par priorité ───────────────────────────────────────
        rouges  = [d for d in dolines if d["priorite"] == "rouge"]
        oranges = [d for d in dolines if d["priorite"] == "orange"]
        jaunes  = [d for d in dolines if d["priorite"] == "jaune"]
        gris    = [d for d in dolines if d["priorite"] == "gris"]

        # ── Clustering spatial rouges + oranges (radius 400 m) ───────────
        cibles_top = rouges + oranges
        clusters = _compute_clusters(cibles_top, radius_m=400.0)

        # Résumé des clusters pour le rapport
        cluster_summary: dict = {}   # label → liste de fids
        for d in cibles_top:
            lbl = clusters.get(d.get("fid"), "·")
            if lbl != "·":
                cluster_summary.setdefault(lbl, []).append(d)

        # ── Rapport Markdown ──────────────────────────────────────────────
        def _table_row(d, rank):
            ratio  = f"{d['ratio_ps']:.3f}" if d.get("ratio_ps") is not None else "—"
            pente  = f"{d['pente_max_bord']:.0f}°" if d.get("pente_max_bord") is not None else "—"
            lisere = "✓" if d.get("lisere") else "—"
            cai    = d.get("cold_air_index")
            cai_str = f"{cai:.3f}" if cai is not None else "—"
            alt    = d.get("altitude_m")
            alt_str = f"{alt:.0f}" if alt is not None else "—"
            coords = f"{int(d['x_l93'])},{int(d['y_l93'])}" if d.get("x_l93") else "—"
            absorb = "✓" if d.get("comp_absorption") else "—"
            geo    = "✓" if d.get("comp_geologie") else "—"
            dist_r = d.get("comp_dist_reseau_m")
            dist_str = f"{int(dist_r)}" if dist_r is not None and not math.isnan(float(dist_r)) else "—"
            clust  = clusters.get(d.get("fid"), "·")
            flag   = " 🔍" if d.get("decouverte") else ""
            flag  += " 🏛️" if d.get("cavite_connue_proche") else ""
            return (f"| {clust} | {rank} | doline_{d['fid']}{flag} | {alt_str} | "
                    f"{d['surface_m2']} | {d['profondeur_m']} | {ratio} | {pente} | "
                    f"{lisere} | {absorb} | {geo} | {cai_str} | "
                    f"{d['score_morpho']} | **{d['score']}** | "
                    f"{dist_str} | {coords} |")

        lines = []
        def w(s=""): lines.append(s)

        w(f"# KarstPro — Analyse secteur « {secteur} »")
        w(f"Date export : {date.today()}  |  Source : {gpkg_path.name}")
        if extra_context:
            w()
            w("## Contexte terrain")
            w()
            w(extra_context)
        w()
        w("---")
        w()
        w("## Résumé")
        w()
        w(f"- **{len(dolines)} dépressions** détectées par LiDAR HD IGN (résolution 1m)")
        w(f"- Réseau karstique connu : **{n_topo} segment(s)** de galeries")
        w(f"- Réseau hydrologique D8 : **{n_hydro} entités**")
        w(f"- Cavités relevées sur le terrain : **{n_cavites}**")
        w(f"- **Cibles de découverte** (prof ≥ 5m, hors réseau connu) : **{n_bonus_hors_couloir}**"
          f" — signalées 🔍 dans les tableaux")
        n_total_cav_ref = n_cav_connues + n_cav_georisques
        if n_total_cav_ref > 0:
            n_proches = sum(1 for d in dolines if d.get("cavite_connue_proche"))
            w(f"- **Cavités référencées dans le secteur** : **{n_total_cav_ref}**"
              f" ({n_cav_connues} utilisateur + {n_cav_georisques} Géorisques BRGM)"
              f" | {n_proches} doline(s) à moins de 20 m — signalées 🏛️")
        w()
        w("## Répartition par priorité")
        w()
        w("| Priorité | Nb | Surf. moy. (m²) | Surf. max (m²) | Prof. moy. (m) | Prof. max (m) | Score moy. | Score max |")
        w("|----------|----|-----------------|----------------|----------------|---------------|------------|-----------|")
        for prio, label in [("rouge","Rouge"), ("orange","Orange"),
                             ("jaune","Jaune"), ("gris","Gris")]:
            s = stats.get(prio)
            if s:
                w(f"| {label} | {s['n']} | {s['surf_moy']} | {s['surf_max']} | "
                  f"{s['prof_moy']} | {s['prof_max']} | {s['score_moy']} | {s['score_max']} |")
        w()
        w("## Critères de scoring")
        w()
        w("**Score final = Bloc A (morphologie uniquement) — 0 à 100 pts [v2.0]**")
        w("Seuils de priorité v2 (recalibrés après validation IKarre 130 cavités) : P1 ≥ 55 | P2 ≥ 35 | P3 ≥ 25 | Hors seuil < 25")
        w("Le score est indépendant du réseau topo connu : un massif vierge score autant qu'un massif exploré.")
        w()
        w("| Composante | Colonne | Poids max | Remarque |")
        w("|------------|---------|-----------|----------|")
        w("| Profondeur | profondeur_m | **30 pts** | Seuils 0.3/1.0/3.0/8.0 m — continu +0.4pt/m > 8m |")
        w("| Surface | surface_m2 | 10 pts | Seuils 50/300/1500 m² |")
        w("| Ratio P/√S | ratio_ps | 8 pts | Potentiel vertical — seuils 0.1/0.2/0.4 |")
        w("| Pente bord | pente_max_bord | 20 pts | p90 anneau 5m — seuils 20/45/70° |")
        w("| Liseré | lisere | 10 pts | Alignement 100m/20° — karst de contact |")
        w("| Absorption | bassin_versant_m2 | 18 pts | Bassin versant D8 — seuils 1k/5k/20k m² |")
        w("| Contact géol. | comp_geologie | 25 pts | Gradient exponentiel τ=250m × facteur karstifiabilité |")
        w("| TPI 500m | tpi_500m | 8 pts | Alt. vs voisines 500m — doline sommitale vs fond vallon |")
        w()
        w("**Colonnes calculées mais hors score (informatives)**")
        w("- `cold_air_index` : indice piégeage air froid [0–1] — redondant avec profondeur/ratio (supprimé du score v2)")
        w("- `circularite` : 4π·S/P² — pénalisait les dolines structurales allongées (supprimé du score v2)")
        w("- `comp_densite_500m` : nb voisines dans 500m — non-discriminant en Barrois dense (supprimé du score v2)")
        w("- `comp_dist_reseau_m` : distance au passage topo le plus proche (NaN si pas de topo)")
        w("- `comp_in_couloir` : booléen — doline dans un buffer 500m autour des galeries connues")
        w("- **Absorb.** ✓ = bassin versant ≥ 5 000 m²  |  **Géol.** ✓ = centroïde sur formation karstifiable")
        w("- **Dist. réseau** : distance en mètres au passage topo le plus proche (— si pas de topo)")
        w()
        _TABLE_HEADER = ("| Cluster | # | ID | Alt. (m) | Surface (m²) | Prof. (m) | P/√S | "
                         "Pente bord | Liseré | Absorb. | Géol. | Air froid | "
                         "Score morpho | Score | Dist. réseau (m) | X_L93,Y_L93 |")
        _TABLE_SEP    = ("|---------|---|----|----------|-------------|-----------|------|"
                         "------------|--------|---------|-------|-----------|"
                         "--------------|-------|------------------|-------------|")

        w("## Clusters géographiques (cibles rouges + oranges, rayon 400 m)")
        w()
        if cluster_summary:
            w("| Cluster | Nb dolines | IDs | Alt. min–max (m) | Centroïde approx. X_L93,Y_L93 |")
            w("|---------|------------|-----|-----------------|-------------------------------|")
            for lbl in sorted(cluster_summary):
                members = cluster_summary[lbl]
                ids = ", ".join(f"doline_{d['fid']}" for d in
                                sorted(members, key=lambda x: x.get("score") or 0, reverse=True))
                xs = [d["x_l93"] for d in members if d.get("x_l93")]
                ys = [d["y_l93"] for d in members if d.get("y_l93")]
                cx = f"{int(sum(xs)/len(xs))}" if xs else "—"
                cy = f"{int(sum(ys)/len(ys))}" if ys else "—"
                alts = [d["altitude_m"] for d in members if d.get("altitude_m") is not None]
                alt_range = f"{min(alts):.0f}–{max(alts):.0f}" if alts else "—"
                w(f"| {lbl} | {len(members)} | {ids} | {alt_range} | {cx},{cy} |")
            n_isolees = sum(1 for d in cibles_top if clusters.get(d.get("fid")) == "·")
            if n_isolees:
                w(f"| · | {n_isolees} | (dolines isolées — > 400 m de toute autre cible) | — | — |")
        else:
            w("Aucun cluster détecté (toutes les cibles rouges/oranges sont à > 400 m les unes des autres).")
        w()
        w("## Cibles prioritaires")
        w()
        w("### Rouges (score >= 75)")
        w()
        if rouges:
            w(_TABLE_HEADER)
            w(_TABLE_SEP)
            for i, d in enumerate(rouges, 1):
                w(_table_row(d, i))
        else:
            w("Aucune doline rouge.")
        w()
        w("### Oranges (score 50-74)")
        w()
        if oranges:
            w(_TABLE_HEADER)
            w(_TABLE_SEP)
            for i, d in enumerate(oranges[:30], 1):
                w(_table_row(d, i))
            if len(oranges) > 30:
                w(f"… et {len(oranges)-30} autres dolines orange.")
        else:
            w("Aucune doline orange.")
        w()
        w(f"### Jaunes : {len(jaunes)} dolines (score 25-49)")
        w(f"### Grises : {len(gris)} dolines (score < 25)")
        w()
        w("## Cibles de découverte 🔍")
        w()
        w("> Dolines avec **profondeur ≥ 5m ET distance au réseau topo > 500m** (ou sans topo renseignée).")
        w("> Fort signal morphologique dans une zone non documentée — potentiel de réseau nouveau.")
        w("> Le score reflète uniquement la morphologie : ces dolines ne sont PAS pénalisées")
        w("> par leur éloignement du réseau connu (le Bloc B positionnel a été supprimé).")
        w()
        if cibles_decouverte:
            w(_TABLE_HEADER)
            w(_TABLE_SEP)
            for i, d in enumerate(sorted(cibles_decouverte,
                                         key=lambda x: x.get("profondeur_m") or 0,
                                         reverse=True), 1):
                w(_table_row(d, i))
        else:
            w("Aucune doline répondant aux critères de découverte (prof ≥ 5m, hors réseau).")
        w()
        if cavites_connues_rows:
            w("## Cavités connues dans le secteur 🏛️")
            w()
            w("> Ces cavités sont déjà répertoriées et (partiellement) explorées.")
            w("> Les dolines marquées 🏛️ dans les tableaux ci-dessus sont à moins de 20 m")
            w("> d'une de ces cavités — elles peuvent être une entrée alternative,")
            w("> un prolongement non exploré, ou un doublon à déprioritiser.")
            w()
            w("| Nom | Type | Découverte | Dernière explo | Explorateurs | Commentaire | Référence |")
            w("|-----|------|------------|----------------|--------------|-------------|-----------|")
            for c in cavites_connues_rows:
                w(f"| {c.get('name','')} | {c.get('type','')} | {c.get('date_disc','')} | "
                  f"{c.get('date_expl','')} | {c.get('explorers','')} | "
                  f"{c.get('comment','')} | {c.get('reference','')} |")

        w()
        w("## Données brutes JSON")
        w()
        w("```json")
        w(json.dumps(dolines, ensure_ascii=False, indent=2))
        w("```")

        report = "\n".join(lines)

        # ── Prompt MLL ───────────────────────────────────────────────────
        has_topo = n_topo > 0
        topo_line = (f"- Réseau karstique connu : {n_topo} segments de galeries (informatif — hors score)"
                     if has_topo else
                     "- Pas de réseau karstique connu dans ce secteur")

        context_parts = []
        if extra_context:
            context_parts.append(extra_context)
        if pendage:
            context_parts.append(f"Direction du pendage / sens de drainage : {pendage}")
        if zones_exclues:
            context_parts.append(f"Zones à exclure de la prospection : {zones_exclues}")
        context_section = ("\n## Contexte terrain spécifique\n\n"
                           + "\n\n".join(context_parts) + "\n") if context_parts else ""

        cavites_connues_section = ""
        n_proches_prompt = sum(1 for d in dolines if d.get("cavite_connue_proche"))

        if cavites_connues_rows or cavites_georisques_rows:
            # Tableau cavités utilisateur
            tableau_utilisateur = ""
            if cavites_connues_rows:
                tableau_utilisateur = "\n### Cavités fournies par l'utilisateur\n\n"
                tableau_utilisateur += "| Nom | Type | Date découv. | Explorateurs | Référence |\n"
                tableau_utilisateur += "|-----|------|--------------|--------------|----------|\n"
                for c in cavites_connues_rows:
                    tableau_utilisateur += (
                        f"| {c.get('name','') or '—'} | {c.get('type','') or '—'} | "
                        f"{c.get('date_disc','') or '—'} | {c.get('explorers','') or '—'} | "
                        f"{c.get('reference','') or '—'} |\n"
                    )

            # Tableau Géorisques
            tableau_georisques = ""
            if cavites_georisques_rows:
                tableau_georisques = "\n### Cavités BRGM Géorisques (inventaire national)\n\n"
                tableau_georisques += "| Nom | Type | Identifiant BRGM | Date validité | Repérage |\n"
                tableau_georisques += "|-----|------|------------------|---------------|----------|\n"
                for c in cavites_georisques_rows:
                    tableau_georisques += (
                        f"| {c.get('nom_cavite','') or '—'} | {c.get('type_cavite','') or '—'} | "
                        f"{c.get('identifiant','') or '—'} | {c.get('date_validite','') or '—'} | "
                        f"{c.get('reperage_geographique','') or '—'} |\n"
                    )

            cavites_connues_section = f"""
## Cavités référencées dans le secteur ({n_total_cav_ref} au total)

{tableau_utilisateur}{tableau_georisques}
Les dolines marquées 🏛️ dans les tableaux sont à moins de 20 m de l'une de ces cavités ({n_proches_prompt} au total).

Pour chaque doline 🏛️ :
- Évalue si c'est un doublon (même phénomène, entrée différente) ou un prolongement potentiel non exploré
- Indique explicitement dans ton analyse quelle cavité connue est concernée et ce que ça implique pour la prospection
- Une cavité "connue" peut être peu ou anciennement explorée — ne l'exclure que si elle est clairement exhaustivement topographiée
- Les cavités Géorisques sont souvent des points d'inventaire administratif peu documentés : traite-les avec plus de recul qu'une cavité fournie par l'utilisateur
"""

        # ── Traçages hydrologiques (réseau perte→résurgence connu) ─────────
        tracages_section = ""
        if tracages_rows:
            tbl = "| Injection (perte) | Résurgence | Colorant | Résultat | Transit | Distance (m) | Inj. L93 | Rés. L93 |\n"
            tbl += "|---|---|---|---|---|---|---|---|\n"
            for t in tracages_rows:
                dist = t.get("distance_m")
                dist_s = f"{dist:.0f}" if isinstance(dist, (int, float)) else "—"
                tbl += (
                    f"| {t.get('point_injection') or '—'} | {t.get('point_sortie') or '—'} | "
                    f"{t.get('colorant') or '—'} | {t.get('resultat') or '—'} | "
                    f"{t.get('temps_transit') or '—'} | {dist_s} | "
                    f"{t['x_inj']:.0f},{t['y_inj']:.0f} | {t['x_res']:.0f},{t['y_res']:.0f} |\n"
                )
            tracages_section = f"""
## Traçages hydrologiques connus ({len(tracages_rows)} tracé(s))

Connexions perte→résurgence établies par traçage colorimétrique. Les coordonnées L93
des points d'injection et de résurgence te permettent de situer ces axes par rapport aux dolines/cibles.

{tbl}
Exploite ce réseau pour l'interprétation :
- Une cible **entre** un point d'injection et une résurgence (sur l'axe de drainage) est probablement sur un drain actif → intérêt accru.
- Une cible **en amont** d'une perte tracée peut alimenter le même système.
- Une zone à fort signal morphologique **sans résurgence connue en aval** peut signaler une résurgence potentielle non identifiée.
- Un résultat **négatif** signifie une absence de connexion démontrée — n'en déduis pas une connexion inverse.
- Le temps de transit renseigne sur le type d'écoulement (rapide = conduit ouvert, lent = réseau noyé/diffus).
"""

        decouverte_section = ""
        if cibles_decouverte:
            ids = ", ".join(f"doline_{d['fid']}" for d in
                            sorted(cibles_decouverte,
                                   key=lambda x: x.get("profondeur_m") or 0,
                                   reverse=True)[:10])
            decouverte_section = f"""
## Cibles de découverte ({n_bonus_hors_couloir} dolines)

**{n_bonus_hors_couloir} dolines** : profondeur ≥ 5m et distantes du réseau topo connu (> 500m ou sans topo).
Ces dolines ont un fort signal morphologique dans une zone non documentée — potentiel de réseau nouveau.
Leur score est identique aux autres : le scoring est purement morphologique, sans pénalité d'éloignement.
Top par profondeur : {ids}
Ces dolines portent le marqueur 🔍 dans les tableaux et ont leur propre section "Cibles de découverte".
Traite-les comme des cibles de prospection autonomes — potentiellement les plus intéressantes pour la découverte.
"""

        # Résumé clusters pour le prompt
        cluster_prompt_lines = []
        for lbl in sorted(cluster_summary):
            members = cluster_summary[lbl]
            ids = ", ".join(f"doline_{d['fid']}" for d in
                            sorted(members, key=lambda x: x.get("score") or 0, reverse=True))
            xs = [d["x_l93"] for d in members if d.get("x_l93")]
            ys = [d["y_l93"] for d in members if d.get("y_l93")]
            cx = f"{int(sum(xs)/len(xs))}" if xs else "?"
            cy = f"{int(sum(ys)/len(ys))}" if ys else "?"
            cluster_prompt_lines.append(f"  - Cluster {lbl} ({len(members)} dolines) : {ids} — centroïde L93 {cx},{cy}")
        clusters_section = ""
        if cluster_prompt_lines:
            clusters_section = (
                "\n## Clusters géographiques pré-calculés (rayon 400 m)\n\n"
                "Ces clusters sont calculés automatiquement — utilise-les comme base pour l'organisation par journée :\n"
                + "\n".join(cluster_prompt_lines) + "\n"
            )

        prompt = f"""Tu es un expert en spéléologie et en analyse de terrain karstique.
Je te fournis les données d'analyse LiDAR HD d'un secteur karstique français pour la prospection spéléologique.

## Contexte du secteur « {secteur} »

- Zone analysée par LiDAR HD IGN (résolution 1m, classification sol/végétation automatique)
- {len(dolines)} dépressions karstiques (dolines) détectées automatiquement
{topo_line}
- **Score = Bloc A v2.0 (morphologie uniquement)** : profondeur (continu > 8m), surface, ratio P/√S, pente bord (p90), liseré, absorption, contact géologique (facteur karstifiabilité), TPI 500m — aucun biais lié au réseau connu{context_section}{cavites_connues_section}{tracages_section}{decouverte_section}{clusters_section}

## Données d'analyse complètes

{report}

---

## Ta mission

**1. Liste priorisée des cibles terrain**
Pour chaque doline rouge et orange (dans l'ordre de score décroissant) :
- Analyse individuelle : pourquoi ce score ? Quel type de phénomène probable (gouffre vertical / perte active / résurgence / galerie fossile) ?
- Regroupement géographique : identifie les clusters de dolines proches à visiter dans la même journée
- Ordre de visite optimal sur 2-3 journées de prospection

**2. Analyse structurale du secteur**
- Y a-t-il des alignements de dolines suggérant une direction de drainage préférentielle ?
- La distribution des scores positionnels révèle-t-elle des zones de prolongement probable du réseau connu ?
- Quelles dolines jaunes méritent quand même une vérification rapide (morphologie particulière) ?

**3. Recommandations terrain pratiques**
- Signes à rechercher sur place pour chaque type de cible (courant d'air, dépôts, morphologie de l'entrée)
- Conditions optimales (saison, météo récente) pour ce type de karst
- Matériel spécifique à prévoir selon les profondeurs détectées

**4. Limites et incertitudes**
- Quelles dolines pourraient être des faux positifs (artefacts LiDAR, terriers, dépressions anthropiques) ?
- Facteurs non capturés par l'analyse automatique à vérifier sur le terrain

**5. Export GPX — à produire obligatoirement**
Génère un fichier GPX complet contenant toutes les cibles rouges et oranges, **triées dans l'ordre de visite optimal** que tu as déterminé (regroupement géographique, pas par score brut).

Format attendu — un bloc de code GPX prêt à copier-coller et enregistrer en `.gpx` :

```xml
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="MLL-KarstPro"
     xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><name>Prospection {secteur}</name></metadata>
  <!-- un <wpt> par cible, dans l'ordre de visite, coordonnées WGS84 -->
  <wpt lat="XX.XXXXXXX" lon="X.XXXXXXX">
    <name>doline_ID_R</name>
    <desc>Journée 1 — Score:XX | prof:Xm | P/sqrtS:X.XXX | [raison spéléo]</desc>
    <sym>Flag, Red</sym>
  </wpt>
  ...
</gpx>
```

Les coordonnées WGS84 sont à calculer depuis les X_L93/Y_L93 fournis dans les tableaux (projection Lambert-93 EPSG:2154 → WGS84 EPSG:4326).
La balise `<desc>` doit indiquer : journée de prospection, score, profondeur, ratio P/√S, et en 1 phrase le type de phénomène probable.

**6. Export CSV QGIS — à produire obligatoirement**
Génère un tableau CSV (séparateur `;`) de toutes les cibles, dans le même ordre de visite que le GPX, avec les colonnes suivantes :

```
name;type;comment;score;priorite;surface_m2;profondeur_m;ratio_ps;x_l93;y_l93;latitude_wgs84;longitude_wgs84
```

- `type` : ta meilleure hypothèse parmi `gouffre/grotte/perte/résurgence/inconnu`
- `comment` : synthèse terrain en 1 phrase (indice principal, signe à rechercher)
- Les autres champs : valeurs numériques issues des données fournies

Ce CSV sera importé dans QGIS via Couche → Ajouter une couche de texte délimité, avec X=`x_l93`, Y=`y_l93`, SCR EPSG:2154.

**7. Rapport de prospection DOCX — à produire obligatoirement**
Génère un script Python complet et autonome utilisant `python-docx` (pip install python-docx).
Ce script, une fois exécuté, crée le fichier `rapport_{secteur}_<date>.docx` dans le dossier courant.

Le rapport DOCX doit contenir :
- **Page de titre** : secteur, date, nb cibles rouges / oranges
- **Résumé exécutif** (bullet points) : contexte, potentiel estimé, points clés de l'analyse
- **Tableau des cibles prioritaires** (toutes les rouges puis top 20 oranges) : colonnes ID, Coordonnées GPS WGS84, Profondeur (m), Surface (m²), Score, Type probable, Indice terrain
- **Organisation de la prospection** : planning par journées avec l'ordre de visite optimal que tu as déterminé
- **Analyse structurale** : alignements, direction de drainage, zones de prolongement probable
- **Recommandations terrain** : matériel, conditions, signes à rechercher
- **Fiche terrain vierge par cible rouge** : une mini-fiche par page (ID, coords, type supposé, case "observation", case "résultat")

Contraintes du script :
- Toutes les données (cibles, coordonnées WGS84 converties, scores, types supposés) doivent être **écrites en dur dans le script** à partir de ton analyse — pas de lecture de fichier externe
- Le script doit être **autonome** : `python rapport_<secteur>.py` suffit
- Utilise des styles Word lisibles : titre H1/H2, tableau avec en-tête coloré, police Arial
- Commence le bloc de code par ```python et termine par ```

Sois concis, pratique, et calibre tes réponses pour un spéléologue expérimenté qui connaît déjà le secteur."""

        feedback.setProgress(70)

        # export_dir / today déjà créés en début de _run (avec le fichier log)
        # Le prompt .txt embarque deja l'integralite du rapport (variable `report`
        # inseree dans `prompt`), donc on n'ecrit plus de .md redondant.
        prompt_path = export_dir / f"mll_prompt_{secteur}_{today}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        feedback.setProgress(80)

        # ── GPX — waypoints cibles prioritaires ───────────────────────────
        cibles = rouges + oranges
        gpx_path = export_dir / f"cibles_{secteur}_{today}.gpx"
        try:
            _write_gpx(cibles, gpx_path, secteur)
            feedback.pushInfo(f"GPX        : {gpx_path}")
        except Exception as e:
            feedback.pushWarning(f"GPX non genere : {e}")

        feedback.setProgress(90)

        # Les couches cibles P1/P2/P3 sont creees et peuplees par la PREPARATION
        # (qfield.write_cibles_from_scored_dolines). L'export MLL ne les reecrit
        # plus : elles seraient identiques et un secteur saisi different creerait
        # des doublons. L'export ne produit que le rapport, le prompt et le GPX.

        feedback.setProgress(100)
        feedback.pushInfo(f"Prompt     : {prompt_path}")
        feedback.pushInfo(
            f"Taille du prompt : {len(prompt):,} caracteres — "
            "ouvrir le .txt, tout selectionner, coller dans MLL. "
            "MLL produira : analyse + GPX ordonne + CSV QGIS + script Python pour le DOCX."
        )
        feedback.pushInfo(f"Log        : {log_file}")
        _elapsed = (datetime.now() - _t0).total_seconds()
        feedback.pushInfo(f"Exécution terminée en {_elapsed:.0f} s")

        return {self.OUTPUT_DIR: str(output_dir)}


# ── Helpers module-level ──────────────────────────────────────────────────────

def _compute_clusters(dolines: list, radius_m: float = 400.0) -> dict:
    """Regroupe les dolines en clusters spatiaux par connexité (distance ≤ radius_m).

    Retourne {fid: label} où label est une lettre (A, B, C…) pour les clusters
    de ≥ 2 dolines, ou "·" pour les dolines isolées.
    """
    import math

    n = len(dolines)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    coords = [(d.get("x_l93") or 0.0, d.get("y_l93") or 0.0) for d in dolines]
    for i in range(n):
        xi, yi = coords[i]
        for j in range(i + 1, n):
            dx = xi - coords[j][0]
            dy = yi - coords[j][1]
            if math.sqrt(dx * dx + dy * dy) <= radius_m:
                union(i, j)

    # Compter les membres par racine
    root_count: dict = {}
    for i in range(n):
        r = find(i)
        root_count[r] = root_count.get(r, 0) + 1

    # Attribuer les lettres uniquement aux clusters de ≥ 2 dolines
    root_label: dict = {}
    letter_idx = 0
    for r in sorted(root_count):
        if root_count[r] >= 2:
            if letter_idx < 26:
                root_label[r] = chr(ord("A") + letter_idx)
            else:
                root_label[r] = f"C{letter_idx - 25}"
            letter_idx += 1

    result = {}
    for i, d in enumerate(dolines):
        r = find(i)
        result[d.get("fid", i)] = root_label.get(r, "·")
    return result


def _l93_to_wgs84(x: float, y: float) -> tuple:
    """Lambert-93 (EPSG:2154) → WGS84 (lon, lat), pur Python sans pyproj.

    Formule LCC 2SP inverse (EPSG méthode 9802) sur ellipsoïde GRS80.
    RGF93 ≡ WGS84 à < 1 m — aucune transformation de datum nécessaire.
    Évite proj_create qui n'est pas thread-safe dans QGIS 4.0.2.
    """
    import math

    a   = 6_378_137.0
    f   = 1 / 298.257_222_101
    e2  = 2*f - f*f
    e   = math.sqrt(e2)

    lam0 = math.radians(3.0)
    phi0 = math.radians(46.5)
    phi1 = math.radians(44.0)
    phi2 = math.radians(49.0)
    E_F  = 700_000.0
    N_F  = 6_600_000.0

    def _m(phi):
        sp = math.sin(phi)
        return math.cos(phi) / math.sqrt(1 - e2 * sp * sp)

    def _t(phi):
        sp = math.sin(phi)
        return math.tan(math.pi/4 - phi/2) / ((1 - e*sp) / (1 + e*sp))**(e/2)

    m1 = _m(phi1); m2 = _m(phi2)
    t1 = _t(phi1); t2 = _t(phi2); t0 = _t(phi0)

    n  = (math.log(m1) - math.log(m2)) / (math.log(t1) - math.log(t2))
    F  = m1 / (n * t1**n)
    r0 = a * F * t0**n

    dE = x - E_F
    dN = r0 - (y - N_F)
    r_prime = math.copysign(math.hypot(dE, dN), n)
    t_prime = (r_prime / (a * F)) ** (1.0 / n)
    theta   = math.atan2(dE, dN)

    lam = theta / n + lam0

    phi = math.pi/2 - 2*math.atan(t_prime)
    for _ in range(10):
        sp = math.sin(phi)
        phi_new = math.pi/2 - 2*math.atan(
            t_prime * ((1 - e*sp) / (1 + e*sp))**(e/2)
        )
        if abs(phi_new - phi) < 1e-12:
            phi = phi_new
            break
        phi = phi_new

    return math.degrees(lam), math.degrees(phi)


def _write_gpx(cibles: list, gpx_path, secteur: str) -> None:
    """Génère un fichier GPX avec un waypoint par cible (rouge puis orange)."""
    import xml.etree.ElementTree as ET

    root = ET.Element("gpx", {
        "version": "1.1",
        "creator": "KarstPro",
        "xmlns": "http://www.topografix.com/GPX/1/1",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": (
            "http://www.topografix.com/GPX/1/1 "
            "http://www.topografix.com/GPX/1/1/gpx.xsd"
        ),
    })
    ET.SubElement(root, "metadata").append(
        _gpx_elem("name", f"KarstPro — {secteur}")
    )

    for d in cibles:
        x = d.get("x_l93")
        y = d.get("y_l93")
        if x is None or y is None:
            continue
        lon, lat = _l93_to_wgs84(float(x), float(y))
        prio = d.get("priorite", "?")
        fid  = d.get("fid", "?")
        score = d.get("score", "?")
        surf  = d.get("surface_m2", "?")
        prof  = d.get("profondeur_m", "?")
        ratio = f"{d['ratio_ps']:.3f}" if d.get("ratio_ps") is not None else "?"
        cai = d.get("cold_air_index")
        cai_str = f"{cai:.3f}" if cai is not None else "—"

        sym = "Flag, Red" if prio == "rouge" else "Flag, Orange"
        wpt = ET.SubElement(root, "wpt", {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"})
        wpt.append(_gpx_elem("name", f"doline_{fid}_{prio[0].upper()}"))
        wpt.append(_gpx_elem("desc",
            f"Score:{score} | {surf}m2 | prof:{prof}m | P/sqrtS:{ratio} | AirFroid:{cai_str} | {prio}"))
        wpt.append(_gpx_elem("sym", sym))
        wpt.append(_gpx_elem("type", f"Prospection karstique — {prio}"))

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(str(gpx_path), encoding="utf-8", xml_declaration=True)


def _gpx_elem(tag: str, text: str):
    import xml.etree.ElementTree as ET
    el = ET.Element(tag)
    el.text = text
    return el


# ── Estimation du pendage régional (problème des trois points) ─────────────────

_COMPASS16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _gpkg_blob_to_geom(blob):
    """Convertit un blob de géométrie GPKG en géométrie shapely (sans pyproj)."""
    if not blob or len(blob) < 8:
        return None
    flags = blob[3]
    env_indicator = (flags >> 1) & 0x07
    env_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    off = 8 + env_sizes.get(env_indicator, 0)
    try:
        from shapely import wkb as swkb
        return swkb.loads(bytes(blob[off:]))
    except Exception:
        return None


def _sample_contact(line, step=10.0):
    """Points (x, y) régulièrement espacés le long d'une ligne/multiligne."""
    from shapely.geometry import LineString, MultiLineString
    if isinstance(line, LineString):
        geoms = [line]
    elif isinstance(line, MultiLineString):
        geoms = list(line.geoms)
    else:
        geoms = [g for g in getattr(line, "geoms", []) if g.geom_type == "LineString"]
    pts = []
    for g in geoms:
        n = max(2, int(g.length // step))
        for i in range(n + 1):
            p = g.interpolate(i / n, normalized=True)
            pts.append((p.x, p.y))
    return pts


def _estimate_dip(gpkg_path, mnt_path, step=10.0):
    """Estime l'azimut et l'angle de pendage régional depuis les contacts
    géologiques et le MNT. Retourne le meilleur contact (R² max) sous forme
    d'un dict {texte, contact, r2, dip, az, compass} ou None.

    Pure sqlite + shapely + rasterio (échantillonnage en coords natives L93,
    pas de reprojection) — compatible avec le thread Processing de QGIS 4.0.2.
    """
    import sqlite3
    import numpy as np
    from shapely.ops import unary_union

    if not Path(mnt_path).exists():
        return None

    con = sqlite3.connect(str(gpkg_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='geologie'")
    if not cur.fetchone():
        con.close()
        return None
    try:
        cur.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name='geologie'")
        r = cur.fetchone()
        gcol = r[0] if r else "geom"
    except Exception:
        gcol = "geom"
    cur.execute("SELECT * FROM geologie LIMIT 0")
    cols = [d[0] for d in cur.description]
    field = "NOTATION" if "NOTATION" in cols else ("CODE_LEG" if "CODE_LEG" in cols else None)
    if field is None:
        con.close()
        return None

    cur.execute(f'SELECT "{field}" AS f, "{gcol}" AS g FROM geologie')
    groups = {}
    for row in cur.fetchall():
        geom = _gpkg_blob_to_geom(row["g"])
        if geom is None:
            continue
        groups.setdefault(str(row["f"]), []).append(geom)
    con.close()
    if len(groups) < 2:
        return None

    forms = {k: unary_union(v) for k, v in groups.items()}
    keys = list(forms)

    import rasterio
    src = rasterio.open(str(mnt_path))
    nodata = src.nodata
    best = None
    try:
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                contact = forms[keys[i]].boundary.intersection(forms[keys[j]].boundary)
                if contact.is_empty:
                    continue
                pts = _sample_contact(contact, step)
                if len(pts) < 8:
                    continue
                z = np.array([v[0] for v in src.sample(pts)], dtype="float64")
                if nodata is not None:
                    z[z == nodata] = np.nan
                ok = np.isfinite(z)
                if ok.sum() < 8:
                    continue
                xy = np.array(pts)[ok]
                zz = z[ok]
                X = np.column_stack([xy[:, 0], xy[:, 1], np.ones(len(xy))])
                coef, *_ = np.linalg.lstsq(X, zz, rcond=None)
                a, b, _c = coef
                zhat = X @ coef
                ss_res = float(np.sum((zz - zhat) ** 2))
                ss_tot = float(np.sum((zz - zz.mean()) ** 2))
                r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
                dip = float(np.degrees(np.arctan(np.hypot(a, b))))
                az = float(np.degrees(np.arctan2(-a, -b)) % 360)
                denivele = float(np.nanmax(zz) - np.nanmin(zz))
                # Garde-fou : rejette les contacts plats/droits/bruités (discordances)
                if not (r2 > 0.4 and denivele > 3.0):
                    continue
                if best is None or r2 > best["r2"]:
                    best = {"r2": r2, "dip": dip, "az": az,
                            "contact": f"{keys[i]}/{keys[j]}", "denivele": denivele}
    finally:
        src.close()

    if best is None:
        return None
    best["compass"] = _COMPASS16[int((best["az"] + 11.25) // 22.5) % 16]
    qual = ("pendage faible" if best["dip"] < 2
            else "pendage modéré" if best["dip"] < 6 else "pendage marqué")
    best["texte"] = (f"{best['compass']} (~{best['az']:.0f}°), "
                     f"{qual} ~{best['dip']:.1f}° (estimé auto. depuis géologie + MNT)")
    return best
