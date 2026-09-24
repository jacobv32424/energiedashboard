# Handleiding: het energiedashboard

Deze handleiding is voor wie het dashboard bekijkt en niet precies weet
wat elk onderdeel betekent. Geen technische kennis nodig.

## Inhoud

[TOC]

## Waarom dit dashboard bestaat

Sinds er zonnepanelen liggen en de stroomprijs niet meer elk jaar
hetzelfde is, maar elk kwartier verandert (net als op de beurs), was de
vraag: *levert dat nou echt iets op, en hoeveel stroom maken die panelen
eigenlijk zelf?* Dit dashboard geeft daar antwoord op, met de cijfers van
je eigen meter — geen slag om de arm, gewoon wat er thuis daadwerkelijk
gebeurt.

## Waar vind je het

**http://192.168.1.163:8421** — werkt op elk apparaat op je eigen
thuisnetwerk (laptop, telefoon, tablet). Er is geen inlog nodig. Let op:
dit werkt alleen thuis op het eigen wifi-netwerk, niet onderweg — deze Pi
(`thuis`) heeft (nog) geen Tailscale, in tegenstelling tot de vorige
locatie (`plex`, verhuisd op 12-09-2026). Links op elke pagina staat een
vast menu met drie onderdelen: **Dashboard**, **Introductie** en
**Handleiding** (deze pagina) — zo ben je altijd één klik verwijderd van
elk van de drie.

## Nieuw hier? Begin bij de Introductie

Naast deze uitgebreide handleiding is er ook een korte, visuele
**Introductie** (via het menu links) — een paar klikbare stappen die in
een paar minuten laten zien wat het dashboard toont, hoe je terugbladert
in de tijd, wat de belangrijkste cijfers betekenen, en waar de data van
vóór juli 2026 vandaan komt. Deze handleiding hier blijft het volledige
naslagwerk voor elk detail; de Introductie is de snelle rondleiding.

## Wat je bovenaan ziet

Vijf (of zes) tegels met de actuele stand:

- **Huidig vermogen** — wat er op dit moment gebeurt. Een negatief getal
  betekent dat je meer stroom opwekt dan verbruikt (teruglevering aan het
  net); een positief getal betekent dat je stroom van het net afneemt.
- **Verbruik vandaag** / **Teruglevering vandaag** — de tellers sinds
  middernacht.
- **Dynamische prijs nu** — wat je op dit moment per kWh betaalt (of
  krijgt) als je op het dynamische tarief zit.
- **Totaal bespaard / extra betaald** — het eerlijke antwoord op de
  hamvraag: had je met het oude, vaste tarief méér of minder betaald over
  de hele periode dat dit dashboard meekijkt? Groen = bespaard, rood/oranje
  = extra betaald.
- **Zelfvoorzienend** — welk deel van je verbruik minimaal door je eigen
  panelen wordt gedekt. Dit is bewust een *ondergrens*, geen exact getal:
  de meter ziet alleen wat er het net op of af gaat, niet de zonnestroom
  die je rechtstreeks zelf verbruikt zonder via het net te gaan. Je
  daadwerkelijke zelfvoorzienendheid ligt dus altijd op zijn minst zo hoog
  als dit percentage.

## Terugbladeren: dag, week, maand, jaar

Bovenin de balk kies je een periode (Dag/Week/Maand/Jaar) en blader je met
de pijltjes terug of vooruit. Het pijltje naar voren is uitgeschakeld
zodra je bij "nu" bent aangekomen — verder dan vandaag kun je niet kijken.

## De grafieken

- **Vermogen** — hoe het vermogen zich door de dag/week heen ontwikkelt.
  Alleen te zien bij "dag" en "week" (bij een hele maand of jaar zegt een
  ogenblikkelijk vermogen niets meer).
- **Zonproductie — typisch per uur** — het gemiddelde over alle gelogde
  dagen samen, per uur van de dag. Laat zien wanneer de panelen doorgaans
  het meest opleveren, los van welke dag je op dat moment bekijkt.
- **Verbruik per periode** — de balken import (van het net) tegenover
  teruglevering (van de zon), gebundeld per uur, dag of maand afhankelijk
  van je gekozen periode.
- **Gasverbruik per periode** — hetzelfde idee als "Verbruik per periode",
  maar dan voor gas. Gas wordt pas sinds 28-07-2026 gelogd, dus periodes
  van daarvoor tonen niets — dat is geen fout, er was toen simpelweg nog
  geen gasdata.

## Geschatte energierekening

Een proforma-optelsom van wat je energie ongeveer heeft gekost (of
opgeleverd): de kale energiekosten plus alle vaste kosten en heffingen uit
je Vandebron-contract (vastrecht, netbeheerkosten, energiebelasting, de
vermindering daarop, de inkoopvergoeding, en — zodra er gasdata is — ook
gas), netjes gegroepeerd onder "Elektriciteit" en "Gas" met een subtotaal
per groep. Een groen bedrag is een vergoeding/vermindering, een gewoon
bedrag is een kostenpost.

**Zelf een startdatum kiezen.** Bovenaan de rekening kies je met het
datumveld "Vanaf" vanaf welke dag de rekening moet meetellen — de
einddatum is altijd "tot heden". Kies je niets, dan begint de rekening bij
het begin van de logging (2 juli 2026).

Kies je een datum vóór 2 juli 2026, dan verschijnt er een apart, duidelijk
gelabeld blok **"Geschat deel"** voor de dagen daarvóór. Voor de periode
1 mei t/m 1 juli 2026 is dit inmiddels **echte data** van je eigen slimme
meter, opgehaald via slimmemeterportal.nl (dat portaal bewaart je
meterstanden al sinds 2015) — geen schatting dus, dat staat er dan ook
letterlijk bij. Voor eventuele dagen die ook daar ontbreken, valt het
dashboard terug op een schatting: je gemiddelde dagverbruik uit de wél
gemeten periode, vermenigvuldigd met de EPEX-dagprijs van die dag. Onder
de tabel staat altijd precies vermeld welk deel echt en welk deel geschat
is.

Onder de tabel staat een staafgrafiek die de gekozen periode opdeelt (per
dag, week, maand of jaar, afhankelijk van hoe lang de periode is) zodat je
het verloop ziet in plaats van alleen het eindtotaal.

Onderaan staan kanttekeningen bij posten die nog een schatting zijn (bijv.
de vaste terugleveringskosten en de inkoopvergoeding op teruglevering, die
allebei afhangen van je jaarverbruik terwijl er nog maar een paar weken
data is — bij Vandebron wordt dat op de jaarafrekening gecorrigeerd, hier
nog niet). Tarieven zijn geldig zolang het huidige contract loopt (tot
1 mei 2027).

### Voorschot

Onder de rekening vul je in wat je maandelijks aan voorschot aan je
energieleverancier betaalt, vanaf welke datum dat geldt. Wijzigt je
voorschot een maand later, vul dan gewoon een nieuwe regel met een nieuwe
ingangsdatum in — de oude regel blijft gewoon staan voor de periode
ervoor. Het dashboard telt vervolgens automatisch op wat je over de
gekozen periode aan voorschot hebt ontvangen, vergelijkt dat met de
werkelijke/geschatte kosten hierboven, en laat zien of je geld terugkrijgt
of moet bijbetalen.

## Tarieven & parameters

Onderaan, achter het uitklap-balkje "⚙ Tarieven & parameters", staan alle
prijzen waarmee gerekend wordt — voor elektriciteit én gas, inclusief de
schijven voor energiebelasting en vaste terugleveringskosten — en waar de
onderliggende data vandaan komt. Niets verstopt.

## Licht/donker

Rechtsboven bij "Donker/licht" schakel je het thema om; je keuze wordt
onthouden voor de volgende keer dat je het dashboard opent.

## Wat het niet doet

- Geen instellingen aanpassen vanuit het dashboard zelf (tarieven wijzig
  je in `config.py`, niet hier).
- Geen sturing van apparaten (dit is alleen een overzicht, geen
  bediening).
- Geen productiegetal los van teruglevering: de meter ziet alleen wat er
  het net op- of afgaat, niet wat de panelen rechtstreeks aan het huis
  zelf leveren zonder via het net te gaan.
