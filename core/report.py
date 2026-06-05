# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
from pathlib import Path
from datetime import date
import geopandas as gpd
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import mm

# Libellés FR des champs (sinon le nom de colonne brut est utilisé).
_LABELS = {
    "name": "Nom", "type": "Type", "reference": "Référence",
    "comment": "Commentaire", "dim_entree_longueur": "Entrée — longueur (m)",
    "dim_entree_largeur": "Entrée — largeur (m)",
    "developpement_estime": "Développement estimé (m)",
    "topographiable": "Topographiable", "lien_topo": "Lien topo",
    "date_disc": "Date découverte", "date_expl": "Date exploration",
    "prot_id": "Protection (id)", "explorers": "Explorateurs",
    "photos": "Photos", "commune": "Commune", "code_insee": "Code INSEE",
    "code_postal": "Code postal", "departement": "Département",
    "code_dept": "Code département",
}
# Ordre d'affichage préféré ; les colonnes hors liste suivent, dans l'ordre source.
_ORDER = list(_LABELS.keys())


def _is_empty(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(v, str) and not v.strip()


def _ordered_columns(cols):
    known = [c for c in _ORDER if c in cols]
    rest = [c for c in cols if c not in _ORDER]
    return known + rest


def generate_report(secteur_name: str,
                    cavites: gpd.GeoDataFrame,
                    output_path: Path) -> Path:
    """Rapport PDF : une fiche par cavité avec TOUS les champs saisis +
    coordonnées L93 et WGS84. Pas de carte (coordonnées en texte)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Rapport de prospection — {secteur_name}", styles["Title"]))
    story.append(Paragraph(f"Date : {date.today():%d/%m/%Y}", styles["Normal"]))
    story.append(Spacer(1, 12))

    n = 0 if cavites is None else len(cavites)
    story.append(Paragraph(f"Cavités relevées ({n})", styles["Heading2"]))
    story.append(Spacer(1, 8))

    if n == 0:
        story.append(Paragraph("Aucune cavité dans ce retour terrain.", styles["Normal"]))
        doc.build(story)
        return output_path

    geom_col = cavites.geometry.name
    attr_cols = _ordered_columns([c for c in cavites.columns if c != geom_col])

    # WGS84 pour l'affichage lat/lon (en plus du L93 natif).
    try:
        wgs = cavites.to_crs("EPSG:4326")
    except Exception:
        wgs = None

    for i, (idx, row) in enumerate(cavites.iterrows()):
        title = row.get("name") if "name" in cavites.columns else None
        if _is_empty(title):
            title = f"Cavité {i + 1}"
        story.append(Paragraph(str(title), styles["Heading3"]))

        data = []
        for c in attr_cols:
            v = row.get(c)
            if _is_empty(v):
                continue
            label = _LABELS.get(c, c)
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            data.append([label, str(v)])

        # Coordonnées
        geom = row.geometry
        if geom is not None and not geom.is_empty:
            data.append(["Coordonnées L93 (X, Y)",
                         f"{geom.x:.1f} ; {geom.y:.1f}"])
            if wgs is not None:
                wg = wgs.geometry.iloc[i]
                if wg is not None and not wg.is_empty:
                    data.append(["Coordonnées WGS84 (lat, lon)",
                                 f"{wg.y:.6f} ; {wg.x:.6f}"])

        if data:
            t = Table(data, colWidths=[60 * mm, 110 * mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(t)
        story.append(Spacer(1, 10))

    doc.build(story)
    return output_path
