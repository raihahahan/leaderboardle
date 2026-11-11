from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageEnhance, ImageOps


@dataclass(frozen=True)
class Detection:
    game: str
    attempts: int | None
    max_attempts: int | None
    success: bool | None
    raw_text: str
    played_on: date | None = None
    played_total: int | None = None
    current_streak: int | None = None
    distribution: tuple[int, ...] | None = None


GAME_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Wordle", ("wordle",)),
    ("Minecraftle", ("minecraftle", "minecraft le")),
    ("Poople", ("poople", "ices to poop")),
    ("Krillion", ("krillion",)),
)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", text.lower()).strip()


def _ocr(frame: np.ndarray, psm: int = 6, *, digits_only: bool = False, scale: float = 2) -> str:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    if scale != 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    config = f"--psm {psm}"
    if digits_only:
        config += " -c tessedit_char_whitelist=0123456789"
    return pytesseract.image_to_string(gray, config=config).strip()


def ocr_image(image_bytes: bytes) -> tuple[str, np.ndarray]:
    original = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes)).convert("RGB"))
    image = original
    if original.width < 1600:
        scale = min(2.5, 1600 / max(original.width, 1))
        image = original.resize((int(original.width * scale), int(original.height * scale)))
    gray = ImageEnhance.Contrast(ImageOps.grayscale(image)).enhance(1.8)
    text = pytesseract.image_to_string(gray, config="--psm 6")
    return text, cv2.cvtColor(np.array(original), cv2.COLOR_RGB2BGR)


def _has_krillion_palette(image: np.ndarray) -> bool:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation, value, hue = hsv[:, :, 1], hsv[:, :, 2], hsv[:, :, 0]
    cyan = ((hue >= 78) & (hue <= 105) & (saturation > 80) & (value > 90)).mean()
    magenta = (((hue >= 160) | (hue <= 5)) & (saturation > 100) & (value > 100)).mean()
    dark = (value < 85).mean()
    return dark > 0.45 and cyan > 0.0003 and magenta > 0.00015


def _classify_game(text: str, image: np.ndarray) -> str | None:
    """Classify from page structure first; title matching is only a fallback."""
    normalized = _normalize(text)
    height, width = image.shape[:2]
    aspect = width / max(height, 1)
    if ("best solution" in normalized and "guesses" in normalized) or (
        "avg extra guesses" in normalized and "play again" in normalized
    ):
        return "Poople"
    if "took" in normalized and "guesses" in normalized and aspect > 2.2:
        return "Minecraftle"
    if ("today s players" in normalized and "dive" in normalized) or (
        aspect > 1.05 and _has_krillion_palette(image)
    ):
        return "Krillion"
    if "guess distribution" in normalized and (
        "played" in normalized or "thanks for playing" in normalized
    ):
        return "Wordle"
    for game, aliases in sorted(GAME_ALIASES, key=lambda pair: -len(pair[0])):
        if any(alias in normalized for alias in aliases):
            return game
    return None


def _parse_attempts(text: str) -> tuple[int, int | None, bool] | None:
    compact = text.replace("|", "/")
    ratio = re.search(r"\b([1-9xX])\s*/\s*([1-9]\d?)\b", compact)
    if ratio:
        maximum = int(ratio.group(2))
        if ratio.group(1).lower() == "x":
            return maximum + 1, maximum, False
        return int(ratio.group(1)), maximum, True
    attempts = re.search(
        r"\b([1-9]\d?)\s*(?:attempts?|tries|guesses?)\b", compact, re.IGNORECASE
    )
    if attempts:
        return int(attempts.group(1)), None, True
    return None


def _extract_poople(text: str) -> tuple[int, int | None, bool] | None:
    match = re.search(r"you\s+used\s+(\d+)\s+guesses", text, re.IGNORECASE)
    return (int(match.group(1)), None, True) if match else None


def _extract_minecraftle(text: str) -> int | None:
    score = re.search(r"took\s+(\d+)\s+guesses", text, re.IGNORECASE)
    return int(score.group(1)) if score else None


def _extract_krillion_score(image: np.ndarray) -> int | None:
    height, width = image.shape[:2]
    # Keep the crop tight around the large score. A taller mobile screenshot
    # otherwise includes the chart and causes single-line OCR to miss the digits.
    crop = image[
        int(height * 0.055):int(height * 0.21),
        int(width * 0.08):int(width * 0.43),
    ]
    for use_threshold in (False, True):
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if use_threshold:
            gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        value = _ocr(gray, psm=13, digits_only=True, scale=4)
        match = re.search(r"\d{2,5}", value)
        if match:
            return int(match.group())
    return None


def _ocr_single_stat(image: np.ndarray, x1: float, x2: float) -> int | None:
    height, width = image.shape[:2]
    crop = image[int(height * 0.30):int(height * 0.39), int(width * x1):int(width * x2)]
    value = _ocr(crop, psm=13, digits_only=True, scale=4)
    match = re.search(r"\d+", value)
    return int(match.group()) if match else None


def _extract_wordle_stats(image: np.ndarray) -> tuple[int | None, int | None, tuple[int, ...] | None]:
    played = _ocr_single_stat(image, 0.15, 0.28)
    current_streak = _ocr_single_stat(image, 0.48, 0.61)
    height, width = image.shape[:2]
    crop = image[int(height * 0.45):int(height * 0.73), int(width * 0.10):int(width * 0.70)]
    text = _ocr(crop, psm=6, digits_only=True, scale=2)
    counts: dict[int, int] = {}
    for line in text.splitlines():
        compact = re.sub(r"\D", "", line)
        if len(compact) >= 2 and compact[0] in "123456":
            counts[int(compact[0])] = int(compact[1:])
    distribution = tuple(counts.get(index, 0) for index in range(1, 7)) if len(counts) >= 4 else None
    return played, current_streak, distribution


def _estimate_grid_rows(image: np.ndarray) -> int | None:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation, value = hsv[:, :, 1], hsv[:, :, 2]
    mask = np.where(
        ((saturation > 45) & (value > 45)) | ((value > 55) & (value < 190)), 255, 0
    ).astype("uint8")
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    centers: list[tuple[float, float, float]] = []
    min_side = max(14, min(image.shape[:2]) * 0.018)
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width >= min_side and height >= min_side and 0.72 <= width / height <= 1.38:
            centers.append((x + width / 2, y + height / 2, (width + height) / 2))
    centers.sort(key=lambda item: item[1])
    rows: list[list[tuple[float, float, float]]] = []
    for tile in centers:
        for row in rows:
            if abs(tile[1] - np.median([entry[1] for entry in row])) <= tile[2] * 0.55:
                row.append(tile)
                break
        else:
            rows.append([tile])
    plausible = [row for row in rows if 4 <= len(row) <= 12]
    return len(plausible) or None


def detect_result(image_bytes: bytes) -> Detection | None:
    text, image = ocr_image(image_bytes)
    game = _classify_game(text, image)
    if not game:
        return None
    if game == "Poople":
        parsed = _extract_poople(text) or _parse_attempts(text)
        if not parsed:
            return None
        attempts, maximum, success = parsed
        return Detection(game, attempts, maximum, success, text.strip())
    if game == "Minecraftle":
        attempts = _extract_minecraftle(text)
        if attempts is None:
            return None
        return Detection(game, attempts, 10, True, text.strip())
    if game == "Krillion":
        score = _extract_krillion_score(image)
        if score is None:
            return None
        return Detection(game, score, None, True, text.strip())
    parsed = _parse_attempts(text)
    if parsed:
        attempts, maximum, success = parsed
        return Detection(game, attempts, maximum, success, text.strip())
    played, current_streak, distribution = _extract_wordle_stats(image)
    if distribution is not None:
        return Detection(
            game, None, 6, None, text.strip(), played_total=played,
            current_streak=current_streak, distribution=distribution,
        )
    rows = _estimate_grid_rows(image)
    if rows:
        return Detection(game, rows, 6, True, text.strip())
    return None
