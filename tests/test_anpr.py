"""Tests ANPR reels : detection de plaque + OCR tesseract sur scenes synthetiques.

Ignores automatiquement si tesseract/opencv est absent (suite toujours verte).
"""
from __future__ import annotations

import numpy as np
import pytest

from ga.vision.anpr import PlateReader, normaliser_plaque, plaque_plausible

cv2 = pytest.importorskip("cv2")

_reader = PlateReader()
pytestmark = pytest.mark.skipif(not _reader.enabled,
                                reason="ANPR indisponible (tesseract absent)")


def scene(plaque_txt: str, y: int = 130, x: int = 130, fs: int = 26) -> "np.ndarray":
    """Scene avec vehicule + plaque encadree ; texte gras sombre sur fond clair."""
    from PIL import Image, ImageDraw, ImageFont

    img = np.full((300, 500, 3), 90, dtype=np.uint8)
    cv2.rectangle(img, (50, 80), (420, 220), (120, 120, 120), -1)   # carrosserie
    cv2.rectangle(img, (x, y), (x + 200, y + 60), (245, 245, 245), -1)
    cv2.rectangle(img, (x, y), (x + 200, y + 60), (20, 20, 20), 3)  # cadre plaque
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fs)
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    ImageDraw.Draw(pil).text((x + 15, y + 14), plaque_txt, fill=(10, 10, 10), font=font)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


class TestNormalisation:
    def test_normalisateur(self):
        assert normaliser_plaque("ab-123 cd") == "AB123CD"
        assert normaliser_plaque("  12.345  ") == "12345"

    def test_plausibilite(self):
        assert plaque_plausible("AB123CD")
        assert not plaque_plausible("123456")  # aucune lettre
        assert not plaque_plausible("ABCDEFG")  # aucun chiffre
        assert not plaque_plausible("AB1")  # trop court
        assert not plaque_plausible("!!")  # caracteres non alphanumeriques seulement


class TestLecturePlaque:
    @pytest.mark.parametrize("attendu", ["1234 AB 56", "AB 123 CD", "45129 A 1", "98765 B 12"])
    def test_lecture_exacte(self, attendu: str):
        lecture = _reader.read(scene(attendu))
        assert lecture is not None, "plaque non detectee"
        assert lecture.plaque == attendu.replace(" ", "")

    def test_petite_plaque_vue_de_loin(self):
        lecture = _reader.read(scene("AB 456 EF", fs=18, y=150, x=200))
        assert lecture is not None and lecture.plaque == "AB456EF"

    def test_bbox_dans_le_cadre_de_la_plaque(self):
        lecture = _reader.read(scene("AB 123 CD"))
        bx, by, bx2, by2 = lecture.bbox
        assert 100 <= bx <= 160 and 100 <= by <= 160
        assert 300 <= bx2 <= 360 and 160 <= by2 <= 210

    def test_aucune_fausse_lecture_sur_bruit(self):
        bruit = np.random.default_rng(7).integers(60, 200, (300, 500, 3), dtype=np.uint8)
        assert _reader.read(bruit) is None

    def test_region_vehicule_seule(self):
        lecture = _reader.read(scene("98765 B 12"), region=(50, 80, 420, 220))
        assert lecture is not None and lecture.plaque == "98765B12"

    def test_dosactive_ne_crash_pas(self):
        lecteur = PlateReader()
        lecteur.enabled = False
        assert lecteur.read(scene("AB 123 CD")) is None
