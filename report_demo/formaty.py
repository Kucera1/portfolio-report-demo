"""České formátování čísel, částek a dat (panel, PDF, texty zpráv)."""

import math
from datetime import date, timedelta

NBSP = " "
DNY = ["po", "út", "st", "čt", "pá", "so", "ne"]


def _chybi(hodnota) -> bool:
    return hodnota is None or (isinstance(hodnota, float) and math.isnan(hodnota))


def cislo(hodnota, desetinna: int = 0) -> str:
    """1234567.5 -> '1 234 568' (mezera jako oddělovač tisíců, čárka jako desetinná)."""
    if _chybi(hodnota):
        return "–"
    text = f"{hodnota:,.{desetinna}f}"
    return text.replace(",", NBSP).replace(".", ",")


def kc(hodnota, desetinna: int = 0) -> str:
    text = cislo(hodnota, desetinna)
    return text if text == "–" else f"{text}{NBSP}Kč"


def kc_znamenko(hodnota, desetinna: int = 0) -> str:
    """Změna v korunách se znaménkem: '+8 805 Kč', '-27 490 Kč'."""
    text = kc(hodnota, desetinna)
    return text if text == "–" or text.startswith("-") else f"+{text}"


def tydny(hodnota) -> str:
    """Na kolik týdnů vydrží zásoba: '12,5', bez prodeje 'neprodává se'."""
    if not _chybi(hodnota) and math.isinf(hodnota):
        return "neprodává se"
    return cislo(hodnota, 1)


def procento(podil, desetinna: int = 1, znamenko: bool = False) -> str:
    """0.125 -> '12,5 %'; se znaménkem '+12,5 %'."""
    if _chybi(podil) or math.isinf(podil):
        return "–"
    vzor = f"{{:{'+' if znamenko else ''}.{desetinna}f}}"
    return vzor.format(podil * 100).replace(".", ",") + NBSP + "%"


def datum(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def datum_kratce(d: date) -> str:
    return f"{DNY[d.weekday()]} {d.day}. {d.month}."


def popis_tydne(pondeli: date) -> str:
    rok, tyden, _ = pondeli.isocalendar()
    return f"Týden {tyden}/{rok} ({datum(pondeli)} – {datum(pondeli + timedelta(days=6))})"
