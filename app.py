"""Ovládací panel: vygenerovat report → zkontrolovat náhled → schválit a odeslat.

Spuštění:  streamlit run app.py
"""

from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from report_demo import formaty
from report_demo.generator import vygeneruj_vse
from report_demo.nacitani import SOUBOR_OBJEDNAVEK, nacti_a_vycisti
from report_demo.report import UKAZATELE, dostupne_tydny, formatuj_hodnotu, spocitej_report
from report_demo.sortiment import NASTAVENI, max_sleva_pri_cilove_marzi, prepocet_slevy, prostor_pro_slevu
from report_demo.schvaleni import (DENIK_ODESLANI, STAV_NAVRH, STAV_ODESLANO, nacti_stav, schval_a_odesli,
                                   uloz_navrh, zahod_navrh)

KOREN = Path(__file__).resolve().parent
VSTUPY = KOREN / "data" / "vstupy"
NAVRHY = KOREN / "vystupy" / "navrhy"
ODESLANO = KOREN / "odeslano"

st.set_page_config(page_title="Týdenní report – Ukázková pražírna", page_icon="☕", layout="wide")

if not (VSTUPY / SOUBOR_OBJEDNAVEK).exists():
    vygeneruj_vse(VSTUPY)

st.title("☕ Týdenní report – Ukázková pražírna")
st.caption("Ukázka s vymyšlenými daty fiktivního e-shopu s kávou. Nic se skutečně neodesílá.")

st.info(
    "**Jak na to:** 1) vyberte týden  →  2) klikněte na **Vygenerovat report**  →  "
    "3) zkontrolujte náhled  →  4) klikněte na **Schválit a odeslat**.  \n"
    "Dokud report neschválíte, je jen návrh a nikam neodejde."
)

data = nacti_a_vycisti(VSTUPY)
tydny = dostupne_tydny(data.objednavky)

vyber, tlacitko = st.columns([3, 1], vertical_alignment="bottom")
tyden = vyber.selectbox("Týden", tydny, format_func=formaty.popis_tydne)
if tlacitko.button("Vygenerovat report", type="primary", width="stretch"):
    with st.spinner("Načítám a čistím data, počítám report…"):
        report = spocitej_report(data, tyden)
        st.session_state["report"] = report
        st.session_state["navrh"] = uloz_navrh(report, NAVRHY)

report = st.session_state.get("report")
navrh = st.session_state.get("navrh")
if report is None:
    st.write("Zatím nebyl vygenerován žádný report.")
    st.stop()

stav = nacti_stav(navrh)

# ------------------------------------------------------------ stav a schválení
st.divider()
st.subheader(f"Report: {formaty.popis_tydne(report.od)}")
if stav["stav"] == STAV_NAVRH:
    st.warning("**Stav: NÁVRH** – report čeká na vaše schválení. Zatím nebyl nikomu odeslán.")
    schvalit, zahodit, _ = st.columns([1, 1, 3])
    if schvalit.button("✅ Schválit a odeslat", type="primary", width="stretch"):
        schval_a_odesli(navrh, ODESLANO)
        st.rerun()
    if zahodit.button("🗑️ Zahodit návrh", width="stretch"):
        zahod_navrh(navrh)
        st.rerun()
elif stav["stav"] == STAV_ODESLANO:
    odeslano_v = datetime.fromisoformat(stav["odeslano"])
    st.success(f"**Stav: ODESLÁNO** – schváleno a odesláno {formaty.datum(odeslano_v)} v {odeslano_v:%H:%M}. "
               f"(Simulace: soubory jsou ve složce odeslano/{stav['slozka_odeslani']}/)")
    with st.expander("Text odeslané zprávy"):
        st.text((ODESLANO / stav["slozka_odeslani"] / "zprava.txt").read_text(encoding="utf-8"))
else:
    st.info("**Stav: ZAHOZENO** – návrh nebyl odeslán. Můžete vygenerovat nový.")

# ------------------------------------------------------------ náhled
st.markdown("#### Hlavní zjištění")
st.markdown("\n".join(f"- {veta}" for veta in report.zjisteni))

popisky = {klic: (popisek, typ) for klic, popisek, typ in UKAZATELE}
sloupce = st.columns(4)
for sloupec, klic in zip(sloupce, ["trzby", "hruba_marze", "provozni_naklady", "provozni_zisk"]):
    popisek, typ = popisky[klic]
    nove, stare = report.ukazatele[klic], report.ukazatele_minule[klic]
    sloupec.metric(popisek, formatuj_hodnotu(nove, typ),
                   delta=formaty.procento(nove / stare - 1, znamenko=True) if stare else None,
                   delta_color="inverse" if klic == "provozni_naklady" else "normal")
    if klic == "provozni_naklady":
        sloupec.caption(f"z toho pravidelné měsíční platby: **{formaty.kc(report.ukazatele['mesicni_platby'])}**")
    if klic == "provozni_zisk":
        bez, bez_minule = report.ukazatele["zisk_bez_mesicnich"], report.ukazatele_minule["zisk_bez_mesicnich"]
        sloupec.caption(f"bez měsíčních plateb: **{formaty.kc(bez)}** "
                        + (f"({formaty.procento(bez / bez_minule - 1, znamenko=True)} proti minulému týdnu)"
                           if bez_minule else ""))


def _tabulka(df: pd.DataFrame, kc=(), procenta=(), zmeny=(), desetiny=(), tydny=()):
    styl = df.style.format({s: formaty.kc for s in kc} | {s: formaty.procento for s in procenta}
                           | {s: (lambda v: formaty.procento(v, znamenko=True)) for s in zmeny}
                           | {s: (lambda v: formaty.cislo(v, 1)) for s in desetiny}
                           | {s: formaty.tydny for s in tydny})
    st.dataframe(styl, hide_index=True, width="stretch")


zalozky = st.tabs(["Tržby po dnech", "Top produkty", "Zboží k doobjednání", "Nezvyklé výkyvy",
                   "Náklady", "Co jsme v datech opravili", "Co se prodává nejvíc a nejméně"])
with zalozky[0]:
    graf = report.denni_trzby.assign(Den=[formaty.datum_kratce(d) for d in report.denni_trzby["Den"]])
    graf["Výkyv"] = graf["Den"].isin(report.vykyvy["Kdy"])
    graf["Tržby (text)"] = graf["Tržby"].map(formaty.kc)
    graf["Obvykle (text)"] = graf["Obvyklá úroveň"].map(formaty.kc)
    osa_kc = alt.Axis(title="Kč", labelExpr="replace(format(datum.value, ',.0f'), /,/g, ' ')")
    popisky_tooltipu = [alt.Tooltip("Den:N"), alt.Tooltip("Tržby (text):N", title="Tržby"),
                        alt.Tooltip("Obvykle (text):N", title="Obvyklá úroveň")]
    sloupce_grafu = alt.Chart(graf).mark_bar(size=34, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("Den:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("Tržby:Q", axis=osa_kc),
        color=alt.condition("datum['Výkyv']", alt.value("#d03b3b"), alt.value("#2a78d6")),
        tooltip=popisky_tooltipu,
    )
    obvykle = alt.Chart(graf).mark_tick(color="#8a8a86", thickness=2, size=40).encode(
        x=alt.X("Den:N", sort=None), y="Obvyklá úroveň:Q", tooltip=popisky_tooltipu)
    st.altair_chart(sloupce_grafu + obvykle, width="stretch")
    st.caption("Šedá čárka = obvyklá úroveň (medián stejného dne v týdnu za předchozí 4 týdny). "
               "Červeně dny s nezvyklým výkyvem.")
    _tabulka(graf[["Den", "Tržby", "Obvyklá úroveň"]], kc=["Tržby", "Obvyklá úroveň"])
with zalozky[1]:
    _tabulka(report.top_produkty, kc=["Tržby"], procenta=["Podíl na tržbách"],
             zmeny=["Změna proti minulému týdnu"])
with zalozky[2]:
    st.caption(f"Stav skladu k {formaty.datum(report.sklad_ke_dni)}. Doporučené množství pokryje 30 dní prodeje.")
    if report.nizka_zasoba.empty:
        st.write("Všechny položky mají dostatečnou zásobu.")
    else:
        _tabulka(report.nizka_zasoba, desetiny=["Prodej za den (ø 4 týdny)", "Vystačí na dní"])
with zalozky[3]:
    if report.vykyvy.empty:
        st.write("Tento týden bez nezvyklých výkyvů.")
    else:
        _tabulka(report.vykyvy, kc=["Skutečnost", "Obvyklá úroveň"], zmeny=["Odchylka"])
with zalozky[4]:
    st.markdown("**Co ovlivnilo provozní zisk**")
    st.caption(report.veta_rozkladu)
    st.dataframe(report.rozklad_zisku.style.format({"Dopad na zisk": formaty.kc_znamenko}),
                 hide_index=True, width="stretch")
    st.markdown("**Náklady podle kategorií**")
    _tabulka(report.naklady_kategorie, kc=["Tento týden", "Průměr za týden (předchozí 4 týdny)"])
with zalozky[5]:
    st.caption(f"Program automaticky opravil nebo vyřadil {len(report.log_detail)} záznamů. "
               "Každá úprava je dohledatelná podle řádku ve zdrojovém souboru.")
    _tabulka(report.log_souhrn)
    with st.expander("Zobrazit všechny úpravy po řádcích"):
        st.dataframe(report.log_detail, hide_index=True, width="stretch")

with zalozky[6]:
    sortiment = report.sortiment
    st.caption(sortiment.poznamky[0])
    st.markdown("**Nejprodávanější zboží**")
    _tabulka(sortiment.nejprodavanejsi, kc=["Tržby"], desetiny=["Prodej za týden (ks)"])
    st.markdown("**Pomalu se točící zboží**")
    if sortiment.pomale.empty:
        st.write("Žádné zboží se netočí pomalu.")
    else:
        _tabulka(sortiment.pomale, kc=["Běžná cena", "Zisk na kus"], procenta=["Marže", "Prostor pro slevu"],
                 desetiny=["Prodej za týden (ks)"], tydny=["Zásoba vydrží (týdnů)"])
    for veta in sortiment.poznamky[1:]:
        st.caption(veta)

    st.markdown("**Kalkulačka slevy**")
    prehled = sortiment.prehled.dropna(subset=["Běžná cena"]).set_index("Kód")
    vychozi = sortiment.pomale["Kód"].iloc[0] if not sortiment.pomale.empty else prehled.index[0]
    produkt = st.selectbox("Produkt", list(prehled.index), index=list(prehled.index).index(vychozi),
                           format_func=lambda kod: prehled.loc[kod, "Produkt"])
    polozka = prehled.loc[produkt]
    sleva = st.slider("Sleva %", min_value=0, max_value=70, value=0, step=1)

    with st.expander("Náklady e-shopu (doprava, reklama, provize, vratky, DPH, cílová marže)"):
        st.caption("Výchozí hodnoty 0 znamenají, že se položka nepočítá. Ceny v ukázkových datech jsou bez DPH.")
        n1, n2 = st.columns(2)
        doprava = n1.number_input("Doprava hrazená e-shopem (Kč na objednávku)", min_value=0.0, step=10.0,
                                  value=float(NASTAVENI["doprava_na_objednavku"]))
        marketing = n2.number_input("Marketing a reklama (Kč na objednávku)", min_value=0.0, step=10.0,
                                    value=float(NASTAVENI["marketing_na_objednavku"]))
        kusu = n1.number_input("Průměrný počet kusů v objednávce", min_value=1.0, step=0.1,
                               value=float(NASTAVENI["kusu_v_objednavce"]))
        platba = n2.number_input("Poplatek za platbu (% z ceny)", min_value=0.0, max_value=100.0, step=0.1,
                                 value=NASTAVENI["platebni_poplatek"] * 100)
        provize = n1.number_input("Provize marketplace nebo srovnávače (% z ceny)", min_value=0.0, max_value=100.0,
                                  step=0.5, value=NASTAVENI["provize"] * 100)
        vratnost = n2.number_input("Vratnost (% objednávek)", min_value=0.0, max_value=100.0, step=0.5,
                                   value=NASTAVENI["vratnost"] * 100)
        vratka = n1.number_input("Náklad na jednu vratku (Kč)", min_value=0.0, step=10.0,
                                 value=float(NASTAVENI["naklad_na_vratku"]))
        cilova = n2.number_input("Cílová marže (% z ceny bez DPH)", min_value=0.0, max_value=99.0, step=1.0,
                                 value=NASTAVENI["cilova_marze"] * 100)
        platce = n1.checkbox("E-shop je plátce DPH", value=NASTAVENI["platce_dph"])
        s_dph = n2.checkbox("Ceny jsou včetně DPH", value=NASTAVENI["ceny_s_dph"])
        sazba = n1.selectbox("Sazba DPH", [21, 12], index=0 if NASTAVENI["sazba_dph"] == 0.21 else 1,
                             format_func=lambda v: f"{v} %")
    nastaveni = NASTAVENI | {
        "doprava_na_objednavku": doprava, "marketing_na_objednavku": marketing, "kusu_v_objednavce": kusu,
        "platebni_poplatek": platba / 100, "provize": provize / 100, "vratnost": vratnost / 100,
        "naklad_na_vratku": vratka, "cilova_marze": cilova / 100, "platce_dph": platce, "ceny_s_dph": s_dph,
        "sazba_dph": sazba / 100,
    }
    cena, nakup, na_kus = polozka["Běžná cena"], polozka["Nákupní cena"], polozka["Náklady na kus"]
    vysledek = prepocet_slevy(cena, nakup, na_kus, sleva / 100, nastaveni=nastaveni)
    puvodni = prepocet_slevy(cena, nakup, na_kus, 0, nastaveni=nastaveni)
    k1, k2, k3 = st.columns(3)
    k1.metric("Nová cena", formaty.kc(vysledek["nova_cena"], 2),
              delta=f"-{formaty.kc(cena - vysledek['nova_cena'], 2)}" if sleva else None,
              delta_color="off")
    k2.metric("Zisk na kus", formaty.kc(vysledek["zisk_na_kus"], 2),
              delta=formaty.kc_znamenko(vysledek["zisk_na_kus"] - puvodni["zisk_na_kus"], 2) if sleva else None)
    k3.metric("Marže", formaty.procento(vysledek["marze"]))
    if vysledek["ve_ztrate"]:
        st.error("Při této slevě by se produkt prodával se ztrátou.")

    prostor = prostor_pro_slevu(cena, nakup, na_kus, nastaveni=nastaveni)
    cilova_sleva = max_sleva_pri_cilove_marzi(cena, nakup, na_kus, nastaveni)
    h1, h2 = st.columns(2)
    h1.metric("Hranice nulového zisku", f"sleva {formaty.procento(prostor)}",
              help="Nejvyšší sleva, při které produkt ještě neprodělává.")
    h1.caption(f"Cena nejméně {formaty.kc(cena * (1 - prostor), 2)}")
    if cilova_sleva["hlaska"]:
        h2.metric(f"Maximální sleva při cílové marži {formaty.procento(nastaveni['cilova_marze'], 0)}", "–")
        h2.warning(cilova_sleva["hlaska"])
    else:
        h2.metric(f"Maximální sleva při cílové marži {formaty.procento(nastaveni['cilova_marze'], 0)}",
                  f"sleva {formaty.procento(cilova_sleva['sleva'])}")
        h2.caption(f"Cena nejméně {formaty.kc(cilova_sleva['nejnizsi_cena'], 2)}")

    st.markdown("Rozpis ceny po slevě (na jeden kus)")
    # Tabulka jen tak široká, jak potřebuje obsah: částky jsou hned vedle popisků a nevypadnou z obrazu.
    st.dataframe(vysledek["rozpis"].style.format({"Kč na kus": lambda v: formaty.kc(v, 2)}),
                 hide_index=True, width="content",
                 column_config={"Kč na kus": st.column_config.TextColumn("Kč na kus", alignment="right")})
    st.caption("Výsledek je orientační. Nezahrnuje fixní náklady (nájem, mzdy, software). "
               "U akční ceny hlídejte pravidlo o nejnižší ceně: sleva se počítá z nejnižší ceny "
               "za posledních 30 dní před slevou.")

# ------------------------------------------------------------ soubory
st.markdown("#### Soubory návrhu")
excel, pdf = (navrh / soubor for soubor in stav["soubory"])
stahnout_excel, stahnout_pdf, _ = st.columns([1, 1, 3])
stahnout_excel.download_button("⬇️ Stáhnout Excel", excel.read_bytes(), file_name=excel.name, width="stretch",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
stahnout_pdf.download_button("⬇️ Stáhnout PDF", pdf.read_bytes(), file_name=pdf.name, mime="application/pdf",
                             width="stretch")

if (ODESLANO / DENIK_ODESLANI).exists():
    with st.expander("Historie odeslaných reportů"):
        st.dataframe(pd.read_csv(ODESLANO / DENIK_ODESLANI, sep=";", encoding="utf-8-sig"), hide_index=True)
