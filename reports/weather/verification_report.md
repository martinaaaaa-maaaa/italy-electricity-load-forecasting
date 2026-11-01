# Verifica dei dati meteo — Francesco

**Stato: parte esplorativa ERA5 verificata. Parte forecast day-ahead ancora aperta.**

## Contenuto

- Intervallo: 2022-01-01T00:00:00Z–2025-12-31T23:00:00Z.
- 35.064 righe orarie; 18 variabili meteo; 1 chiave `timestamp_utc`.
- Sei città; temperatura (°C), umidità relativa (%) e copertura nuvolosa (%).
- Fonte: Open-Meteo Historical Weather API; modello esplicito ERA5; rianalisi a posteriori.
- Download effettuato da Francesco tramite Colab il 1 novembre 2026; 288 risposte mensili conservate con metadati e checksum.

## Controlli completati

| Controllo | Esito |
| --- | --- |
| Griglia oraria UTC e copertura delle sei città | Completa |
| Timestamp duplicati | 0 |
| Valori mancanti e ore assenti | 0 |
| Superamenti delle soglie impostate | 0 |
| Hash delle risposte originali verificati | 288 su 288 |
| Confronto diretto CSV/risposte originali | 631.152 celle su 631.152 identiche |
| Date di cambio ora in Europe/Rome | 4 giornate di 23 ore e 4 di 25 ore, nei giorni interni al periodo |
| Ricostruzione offline del CSV | Riuscita; hash identico al file caricato da Francesco |
| Test automatici del codice | 12 superati |

Nessun valore è stato interpolato, imputato, sostituito con zero o eliminato. L'assenza di NaN è una proprietà delle risposte ricevute, non il risultato di una correzione applicata. Gli originali sono conservati byte per byte. I controlli strutturali e il confronto con gli originali non costituiscono validazione contro misure di stazione indipendenti.

## Temperature

| Città | Media 2022–2025 (°C) | Minimo orario (°C) | Massimo orario (°C) |
| --- | --- | --- | --- |
| Milano | 15.25 | -4.0 | 38.8 |
| Torino | 15.03 | -4.2 | 39.5 |
| Bologna | 15.76 | -4.3 | 38.8 |
| Roma | 17.79 | -1.0 | 39.8 |
| Napoli | 17.99 | 0.9 | 35.6 |
| Palermo | 20.10 | 2.8 | 43.2 |

Le medie sono calcolate su tutte le ore UTC del periodo. I grafici mostrano quattro cicli stagionali, con massimi estivi e minimi invernali; le città settentrionali presentano inverni più freddi e Palermo medie più alte nei dodici mesi. Non emergono discontinuità macroscopiche nell'ispezione dei due grafici. Questo riscontro visivo non esclude errori più sottili o differenze rispetto alla meteorologia locale.

Il massimo orario di Palermo (43,2 °C) è conservato e rientra nella soglia prudenziale usata. Non è stato confrontato con una stazione locale. Le temperature derivano da punti su una griglia modellistica e non descrivono esattamente ogni quartiere della città.

## Scelte e limiti

Le coordinate effettivamente restituite differiscono dai punti richiesti per effetto della griglia del prodotto. Entrambe le coordinate e l'elevazione restituita sono registrate in `provenance.csv` e `independent_audit.json`. Non si tratta di medie regionali né di misure di stazione.

Soglie: −50–60 °C per temperatura (filtro prudenziale), 0–100% per umidità e copertura nuvolosa. Nessun superamento. Le medie giornaliere e mensili compaiono solo nei grafici; il CSV è orario. I raggruppamenti grafici sono UTC. Le giornate locali ai due estremi dell'intervallo UTC sono parziali: allineare il confine temporale ai dati elettrici prima del merge.

**ERA5 non era disponibile al momento della previsione day-ahead delle date storiche. Non usare questo CSV come meteo noto in anticipo nel backtest finale.** Nessun file forecast è stato creato né riempito con rianalisi. Radiazione solare facoltativa esclusa; durata del giorno affidata al calendario.

Il notebook include grafici e tabelle generati dai dati reali. Le celle sono state rieseguite sequenzialmente tramite Python, con lettura offline dei JSON originali; le immagini PNG sono incorporate negli output. In questo ambiente non è disponibile un kernel Jupyter. L'esecuzione del download in Colab è stata effettuata da Francesco.

## Riproduzione

Dalla cartella principale del progetto, dopo aver installato le dipendenze:

```bash
python notebooks/francesco/weather_pipeline.py --offline
python notebooks/francesco/verify_weather.py
python -m unittest discover -s notebooks/francesco/tests -v
```

Il primo comando ricrea CSV, report e grafici; i JSON originali restano intatti. Il secondo confronta ogni valore con gli originali, leggendo senza modificare i dati. Il terzo usa fixture sintetiche in cartelle temporanee, eliminate al termine.

## Parte ancora aperta

Concordare con il gruppo l'ora limite della previsione elettrica e l'intervallo effettivo dei dati di Marco. Verificare poi un archivio di previsioni meteo effettivamente disponibili entro tale ora, distinguendo run operativi e hindcast. Salvare le previsioni in un file separato con identificazione del run, città e ora target. I dettagli sono in `forecast_feasibility.md`.

Fonte e documentazione: https://open-meteo.com/en/docs/historical-weather-api . Verifica effettuata il 1 novembre 2026. Fonte dati: Open-Meteo, ERA5 (ECMWF/Copernicus); condizioni di attribuzione: https://open-meteo.com/en/licence .
