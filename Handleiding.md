# Handleiding: het energiedashboard

Deze handleiding is voor wie het dashboard bekijkt en niet precies weet
wat elk onderdeel betekent. Geen technische kennis nodig.

## Waarom dit dashboard bestaat

Sinds er zonnepanelen liggen en de stroomprijs niet meer elk jaar
hetzelfde is, maar elk kwartier verandert (net als op de beurs), was de
vraag: *levert dat nou echt iets op, en hoeveel stroom maken die panelen
eigenlijk zelf?* Dit dashboard geeft daar antwoord op, met de cijfers van
je eigen meter — geen slag om de arm, gewoon wat er thuis daadwerkelijk
gebeurt.

## Waar vind je het

**http://plex:8421** — werkt op elk apparaat op je eigen netwerk (laptop,
telefoon, tablet). Er is geen inlog nodig.

## Wat je bovenaan ziet

Vier (of vijf) tegels met de actuele stand:

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
- **Vast vs. dynamisch tarief** — de opgetelde kosten sinds het begin van
  de logging, op de oude manier (vast tarief) versus wat je daadwerkelijk
  op het dynamische tarief hebt betaald. Deze grafiek kijkt altijd naar de
  hele geschiedenis, ongeacht welke periode je hierboven hebt gekozen.

## Geschatte energierekening

Een proforma-optelsom van wat je energie sinds het begin van de logging
ongeveer heeft gekost (of opgeleverd): de kale energiekosten plus alle
vaste kosten en heffingen uit je Vandebron-contract (vastrecht,
netbeheerkosten, energiebelasting, de vermindering daarop, de
inkoopvergoeding, en — zodra er gasdata is — ook gas). Onder de tabel
staan kanttekeningen bij posten die nog een schatting zijn (bijv. de
vaste terugleveringskosten en de inkoopvergoeding op teruglevering, die
allebei afhangen van je jaarverbruik terwijl er nog maar een paar weken
data is — bij Vandebron wordt dat op de jaarafrekening gecorrigeerd, hier
nog niet). Tarieven zijn geldig zolang het huidige contract loopt (tot
1 mei 2027).

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
