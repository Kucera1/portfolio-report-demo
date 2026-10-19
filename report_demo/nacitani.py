"""Načtení tří nesourodých zdrojů a jejich vyčištění do jedné datové sady."""

from datetime import date
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from .cisteni import LogZmen, je_prazdne, vycisti_naklady, vycisti_objednavky, vycisti_sklad

SOUBOR_OBJEDNAVEK = "objednavky.csv"
SOUBOR_NAKLADU = "naklady.xlsx"
SOUBOR_SKLADU = "sklad.csv"


class VycistenaData(NamedTuple):
    objednavky: pd.DataFrame
    naklady: pd.DataFrame
    sklad: pd.DataFrame
    log: LogZmen
    sklad_ke_dni: date


def nacti_objednavky_csv(cesta: Path) -> pd.DataFrame:
    """Export z e-shopu: středník, desetinná čárka, UTF-8 s BOM (tak ho otevře i Excel)."""
    df = pd.read_csv(cesta, sep=";", dtype=str, encoding="utf-8-sig", skip_blank_lines=False)
    df["radek"] = range(2, len(df) + 2)
    return df


def nacti_naklady_xlsx(cesta: Path) -> pd.DataFrame:
    """Ručně vedená tabulka: nad záhlavím může být nadpis, uprostřed prázdné řádky."""
    surova = pd.read_excel(cesta, header=None, dtype=object)
    hlavicka = next(
        (i for i, radek in surova.iterrows()
         if any(isinstance(h, str) and h.strip().lower() == "datum" for h in radek)),
        None,
    )
    if hlavicka is None:
        raise ValueError("V tabulce nákladů chybí řádek se záhlavím „Datum“.")
    data = surova.iloc[hlavicka + 1:].copy()
    data.columns = [f"sloupec_{j}" if je_prazdne(h) else str(h).strip()
                    for j, h in enumerate(surova.iloc[hlavicka])]
    data["radek"] = data.index + 1  # číslo řádku tak, jak ho uživatel vidí v Excelu
    return data


def nacti_sklad_csv(cesta: Path) -> pd.DataFrame:
    df = pd.read_csv(cesta, sep=",", dtype=str, encoding="utf-8", skip_blank_lines=False)
    df["radek"] = range(2, len(df) + 2)
    return df


def nacti_a_vycisti(slozka: Path) -> VycistenaData:
    slozka = Path(slozka)
    log = LogZmen()
    sklad = vycisti_sklad(nacti_sklad_csv(slozka / SOUBOR_SKLADU), log)
    objednavky = vycisti_objednavky(nacti_objednavky_csv(slozka / SOUBOR_OBJEDNAVEK),
                                    sklad["sku"].tolist(), log)
    naklady = vycisti_naklady(nacti_naklady_xlsx(slozka / SOUBOR_NAKLADU), log)
    # Sklad je snímek z posledního exportu; bereme ho ke dni poslední objednávky.
    ke_dni = objednavky["den"].max().date() if not objednavky.empty else date.today()
    return VycistenaData(objednavky, naklady, sklad, log, ke_dni)
