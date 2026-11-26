"""ANPR : lecture reelle de plaques d'immatriculation (OpenCV 5 + OCR tesseract).

Chaine : candidats de plaques par contours/morphologie (dense de bords horizontaux,
ratio large/hauteur 1.8-7.5) -> redressement + binarisation Otsu -> OCR tesseract
(liste blanche A-Z0-9) -> normalisation et validation du format.

Le lecteur se degrade proprement : sans tesseract, `enabled` vaut False et `read()`
retourne None (le dossier d'infraction reste valide sans plaque).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ga.core.logging import get_logger

log = get_logger("ga.vision.anpr")

cv2 = None
try:  # le module reste importable sans opencv (outils de build)
    import cv2 as _cv2
    cv2 = _cv2
except ImportError:  # pragma: no cover
    pass

try:
    import pytesseract as _pytesseract
    _pytesseract.get_tesseract_version()
    pytesseract = _pytesseract
    _OCR_DISPONIBLE = True
except Exception:  # binaire absent ou pytesseract manquant
    pytesseract = None
    _OCR_DISPONIBLE = False

_MOTIF_PLAQUE = re.compile(r"^[A-Z0-9]{4,10}$")
_BLANC = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


@dataclass
class PlateReading:
    plaque: str
    score: float
    bbox: tuple[int, int, int, int]
    brut: str


def normaliser_plaque(texte: str) -> str:
    """Uppercase + suppression des separateurs usuels (espaces, tirets, points)."""
    return re.sub(r"[^A-Z0-9]", "", (texte or "").upper())


def plaque_plausible(plaque: str) -> bool:
    """Format plausible : 4-10 caracteres alphanumeriques, chiffres ET lettres."""
    if not _MOTIF_PLAQUE.match(plaque):
        return False
    return any(c.isdigit() for c in plaque) and any(c.isalpha() for c in plaque)


class PlateReader:
    """Lecteur de plaques offline (aucune donnee ne quitte la machine)."""

    name = "anpr_contours_tesseract"

    def __init__(self, lang: str = "eng") -> None:
        self.lang = lang
        self.enabled = cv2 is not None and _OCR_DISPONIBLE
        if not self.enabled:
            log.warning("ANPR indisponible (opencv/tesseract absent) : dossiers sans plaque")

    # ---- lecture -------------------------------------------------------------
    def read(self, frame: "np.ndarray", region: Sequence[int] | None = None) -> PlateReading | None:
        """Lire la plaque la plus probable (region = bbox vehicule en (x1,y1,x2,y2))."""
        if not self.enabled or frame is None:
            return None
        zone = frame
        decalage = (0, 0)
        if region is not None and len(region) == 4:
            x1, y1, x2, y2 = [int(v) for v in region]
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 - x1 < 20 or y2 - y1 < 10:
                return None
            zone = frame[y1:y2, x1:x2]
            decalage = (x1, y1)
        h_z, w_z = zone.shape[:2]
        # priorite aux rectangles "ressemblant a une plaque" (ratio 2-6, surface < 20 %)
        proches, autres = [], []
        for cand in self._candidats(zone):
            px, py, pw, ph = cand
            ratio = pw / ph
            (proches if 2.0 <= ratio <= 6.0 and pw * ph <= 0.2 * w_z * h_z else autres).append(cand)
        meilleure: PlateReading | None = None
        for groupe in (proches, autres):
            for (px, py, pw, ph) in groupe:
                # deux rognages : interieur (le cadre noir perturbe l'OCR) et complet
                dx, dy = int(pw * 0.08), int(ph * 0.12)
                for crop_zone in (zone[py + dy:py + ph - dy, px + dx:px + pw - dx],
                                  zone[py:py + ph, px:px + pw]):
                    crop = self._preparer(crop_zone)
                    if crop is None or crop.size == 0:
                        continue
                    texte, score = self._ocr(crop)
                    plaque = normaliser_plaque(texte)
                    if not plaque_plausible(plaque):
                        continue
                    reading = PlateReading(plaque, score, (px, py, px + pw, py + ph), texte.strip())
                    if meilleure is None or reading.score > meilleure.score or \
                            (reading.score == meilleure.score and len(plaque) > len(meilleure.plaque)):
                        meilleure = reading
                if meilleure is not None:  # un candidat plausible a repondu : on s'arrete la
                    break
            if meilleure is not None:
                break
        if meilleure:
            bx, by, bx2, by2 = meilleure.bbox
            meilleure.bbox = (bx + decalage[0], by + decalage[1],
                              bx2 + decalage[0], by2 + decalage[1])
        return meilleure

    # ---- interne ---------------------------------------------------------------
    def _candidats(self, zone: "np.ndarray") -> list[tuple[int, int, int, int]]:
        """Rectangles candidats : bords horizontaux denses, ratio plaque, surface minimale.

        Deux passes Canny (souple + stricte) pour un meilleur rappel, dedoublonnees.
        """
        gris = cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)
        gris = cv2.equalizeHist(gris)
        noyau = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))
        h, w = gris.shape[:2]
        surface_min = 0.0009 * w * h
        candidats: list[tuple[int, int, int, int]] = []
        for seuils in ((50, 150), (80, 200)):
            bords = cv2.Canny(gris, *seuils)
            dense = cv2.morphologyEx(bords, cv2.MORPH_CLOSE, noyau)
            # RETR_LIST et non EXTERNAL : sous OpenCV 5, une plaque encadree par la
            # carrosserie est un contour enfant que EXTERNAL ecarte
            contours, _ = cv2.findContours(dense, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                x, y, cw, ch = cv2.boundingRect(c)
                if ch < 12 or cw < 44 or ch > h * 0.6:
                    continue
                ratio = cw / ch
                if 1.8 <= ratio <= 7.5 and cw * ch >= surface_min:
                    candidats.append((x, y, cw, ch))
        # dedoublonnage des recouvrements (les deux passes trouvent les memes rectangles)
        uniques: list[tuple[int, int, int, int]] = []
        for cand in sorted(candidats, key=lambda b: b[2] * b[3], reverse=True):
            if all(self._iou(cand, u) < 0.6 for u in uniques):
                uniques.append(cand)
        return uniques[:4]

    @staticmethod
    def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1, y1 = max(ax, bx), max(ay, by)
        x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        inter = (x2 - x1) * (y2 - y1)
        return inter / float(aw * ah + bw * bh - inter)

    def _preparer(self, plaque_img: "np.ndarray"):
        """Gris agrandi (largeur ~300 px) + marge blanche : tesseract binarise mieux en
        interne et ne perd plus les glyphes de bord."""
        if plaque_img.size == 0:
            return None
        gris = cv2.cvtColor(plaque_img, cv2.COLOR_BGR2GRAY)
        h, w = gris.shape[:2]
        facteur = min(4, max(1, int(np.ceil(300 / max(1, w)))))
        if facteur > 1:
            gris = cv2.resize(gris, (w * facteur, h * facteur), interpolation=cv2.INTER_CUBIC)
        return cv2.copyMakeBorder(gris, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)

    def _ocr(self, binaire: "np.ndarray") -> tuple[str, float]:
        config = f"--oem 3 --psm 7 -c tessedit_char_whitelist={_BLANC}"
        try:
            data = pytesseract.image_to_data(binaire, lang=self.lang, config=config,
                                             output_type=pytesseract.Output.DICT)
        except Exception as exc:
            log.warning("echec OCR : %s", exc)
            return "", 0.0
        textes, confs = [], []
        for txt, conf in zip(data.get("text", []), data.get("conf", [])):
            txt = (txt or "").strip()
            if txt:
                textes.append(txt)
                try:
                    confs.append(float(conf))
                except (TypeError, ValueError):
                    pass
        score = float(np.mean(confs)) / 100.0 if confs and max(confs) > 0 else \
            (0.5 if textes else 0.0)
        # certains builds tesseract renvoient conf 0 : score de reserve pour un texte plausible
        return " ".join(textes), score
