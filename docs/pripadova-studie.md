# Případová studie: týdenní report bez ručního skládání čísel

*Ukázka na vymyšlených datech fiktivního e-shopu s kávou „Ukázková pražírna“. Nejde o reálného klienta.*

## Výchozí situace

Malý e-shop má čísla na třech místech: export objednávek z e-shopu, ručně vedenou tabulku nákladů a skladový soubor. Každý týden je někdo musí slepit dohromady, aby majitel věděl, jak se firmě daří. Je to zdlouhavé a snadno se v tom udělá chyba. Formáty dat se různí, kategorie nákladů mají překlepy a v souborech se objevují duplicity a mezisoučty.

## Co jsem postavil

Automatický týdenní report, který:

- načte všechny tři zdroje tak, jak jsou, bez změny zvyklostí,
- vyčistí je (sjednotí formáty, opraví překlepy, vyřadí duplicity) a **zapíše každou úpravu do logu**, aby bylo vidět, co se změnilo,
- spočítá přehled: tržby, náklady, marži, zboží k doobjednání a neobvyklé výkyvy,
- připraví Excel a PDF,
- **nic neodešle, dokud ho člověk neschválí.**

## Příklad toho, co report ukáže

V týdnu 41/2026 klesl provozní zisk o 64 %. Při pohledu na samotné číslo by to vypadalo jako vážný problém. Report ale pokles rozložil. Většinu poklesu způsobilo načasování pravidelných plateb (tento týden mzdy, minulý týden nájem). Zisk bez nich klesl jen o 13,7 %, hlavně kvůli drahé marketingové kampani. Majitel tak nevidí jen číslo, ale i důvod.

Report také upozornil na den s výpadkem e-shopu, na velkou firemní objednávku a na čtyři položky, které je potřeba doobjednat.

## Co se prodává nejvíc a nejméně

Majitele nezajímá jen to, co se prodává dobře. Stejně důležité je zboží, které leží na skladě a blokuje peníze.

Report proto ukáže nejprodávanější zboží i zboží, které se točí pomalu: kolik ho je na skladě, na kolik týdnů zásoba vystačí, jakou má marži po poplatcích a jaký je prostor pro slevu, tedy nejvyšší sleva, při které se produkt ještě neprodělá. Prostor pro slevu je spočítaný fakt, ne doporučení.

K pomalu se točícímu zboží report přidá slovní návrh „zvaž slevu“, „zvaž vyřazení“ nebo „zvaž balíček“, vždy s krátkým vysvětlením, proč. Návrhy neobsahují žádná procenta a rozhoduje o nich majitel. V panelu je navíc kalkulačka: u vybraného produktu nastavíte slevu a hned vidíte novou cenu, marži a zisk na kus.

V ukázkových datech má Keňa AA 250 g na skladě 900 ks, zásoba vydrží 23,2 týdne a marže je 41 %, proto report navrhuje zvážit slevu. Kávový sirup se téměř neprodává a má nízkou marži (11 %), proto navrhuje zvážit vyřazení. Jde o vymyšlená data fiktivní firmy.

## Jak by to vypadalo u skutečného klienta

1. Na jeho datech pustíme report několik týdnů souběžně s ručním postupem a porovnáme čísla.
2. Doplním kategorie a názvy tak, jak je firma skutečně používá.
3. Po schválení se report odešle e-mailem na předem dané adresy.
4. Návrh se připravuje automaticky, např. každé pondělí ráno.

Data zůstávají u klienta.

## Co ukázka neřeší

Skutečné odesílání, přihlašování a role, DPH, slevy a vratky. Prahy pro neobvyklé výkyvy jsou jednoduchá pravidla, která je potřeba doladit na datech konkrétní firmy.

## Jak postupuji

Používám AI nástroje, ale zadání, návrh, kontrolu a testování dělám sám. Ukázka má 40 automatických testů a kód je veřejně na GitHubu: [portfolio-report-demo](https://github.com/Kucera1/portfolio-report-demo).

**Jak to děláte u vás?** Napište mi, jak dnes sestavujete týdenní nebo měsíční přehled, a řeknu vám, jestli a za kolik to půjde zautomatizovat.

Jaroslav Kučera
