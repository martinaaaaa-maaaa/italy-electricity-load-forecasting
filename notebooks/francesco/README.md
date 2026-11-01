# Meteo — Francesco

**Consegna esplorativa verificata: ERA5, sei città, dati orari 2022–2025.**

Il file principale è `data/processed/weather_clean.csv`: 35.064 righe, una chiave UTC e 18 colonne meteo. Nessun valore mancante, nessun timestamp duplicato e nessun superamento delle soglie definite. Il CSV è stato confrontato con tutte le risposte originali: 631.152 valori identici. Gli originali sono conservati senza modifiche.

## Da leggere per primo

Apri `weather_francesco.ipynb`: contiene spiegazioni, codice, tabelle e i due grafici già calcolati sui dati reali. Puoi visualizzarlo anche senza rieseguire il download. Il riepilogo dei controlli è in `reports/weather/verification_report.md`.

**Questa è rianalisi meteorologica a posteriori. La parte sulle previsioni archiviate per il modello day-ahead resta da completare.** Il CSV non può essere usato come meteo disponibile in anticipo nel backtest finale. La distinzione è documentata anche nel dizionario, nei metadati e nel notebook.

## Trasferimento nel repository, quando concordato con il gruppo

Il pacchetto rispetta questi percorsi, partendo dalla cartella principale del progetto:

| Percorso | Contenuto |
| --- | --- |
| `notebooks/francesco/` | Notebook completo, script, verifica indipendente, requisiti e test della propria parte |
| `data/raw/weather_reanalysis/` | 288 risposte JSON originali e 288 file di metadati |
| `data/processed/weather_clean.csv` | Tabella oraria pulita, qualificata come rianalisi |
| `reports/weather/` | Report NaN, intervalli mancanti, anomalie, grafici, provenienza, dizionario, audit e limiti forecast |

All'interno del pacchetto la cartella `weather_francesco/` rappresenta la radice del progetto: trasferiscine i contenuti mantenendo i percorsi. Verifica prima se esistono già file con gli stessi nomi, per evitare di sostituire modifiche del gruppo. Non occorre cambiare il file condiviso `download_weather.py`, il README generale o gli altri notebook.

Prima di integrare il CSV, confermare con Marco l'intervallo delle serie elettriche. Il periodo di questa estrazione è definito in UTC, non con mezzanotte italiana. Controllare che non vengano perse o aggiunte ore nel merge. Le istruzioni del gruppo prevedono lavoro su `main`, pull prima e commit/push dopo; qui non è stata effettuata alcuna modifica al repository.

## Riproduzione locale

Da una cartella con la stessa struttura del pacchetto, con Python 3.10 o superiore:

```bash
python -m pip install -r notebooks/francesco/requirements_weather.txt
python notebooks/francesco/weather_pipeline.py --offline
python notebooks/francesco/verify_weather.py
```

Il primo comando installa le dipendenze. Il secondo usa i dati originali già inclusi per ricostruire CSV, report e grafici. Il terzo legge i file e li verifica senza modificarli.

Per ripetere il download senza i JSON già disponibili:

```bash
python notebooks/francesco/weather_pipeline.py
```

I file esistenti nella cache sono riutilizzati senza riscriverli. Per un altro periodo si possono specificare `--start YYYY-MM-DD --end YYYY-MM-DD`; gli estremi sono inclusi e il nuovo intervallo sostituisce il CSV elaborato. Conservare copie distinte quando si lavora con intervalli differenti.

Per i test offline:

```bash
python -m unittest discover -s notebooks/francesco/tests -v
```

Tutti e 12 i test sono passati. Le fixture sintetiche dei test sono temporanee e non costituiscono i dati consegnati.

## Uso su Colab

La versione allegata ha `OFFLINE = True`, perché usa le risposte originali incluse. Se carichi soltanto il notebook e vuoi riscaricare i dati in una nuova sessione Colab, cambia `OFFLINE = False` nella sezione 2. Con il pacchetto estratto su Jupyter, lascia `True`. Il notebook è autonomo e include il codice dello script.

## Regole di elaborazione

- Modello esplicito ERA5, temperatura in °C, umidità e nuvolosità in percentuale.
- Chiave `timestamp_utc` nel formato `2025-07-01T14:00:00Z`.
- Colonne come `temp_milano_c`, `humidity_milano_pct` e `cloud_cover_milano_pct`.
- Nessun riempimento, interpolazione, sostituzione dei mancanti con zero o eliminazione automatica dei valori sospetti.
- Nessuna imputazione introdotta dal codice; il prodotto ERA5 resta una ricostruzione modellistica del fornitore.
- Duplicati o unità inattese bloccano l'elaborazione. Le ore assenti sono rappresentate con celle vuote.
- Soglie di segnalazione: temperatura −50–60 °C; umidità e nuvolosità 0–100%. La soglia termica è prudenziale per queste città.
- Le coordinate richieste e quelle restituite sono registrate: i punti rappresentano una griglia, non stazioni di misura né medie territoriali.
- Radiazione solare esclusa perché facoltativa; durata del giorno demandata alle feature di calendario.

## Passaggio successivo: forecast

Concordare l'ora limite della previsione elettrica. Verificare quindi copertura e natura delle previsioni archiviate, inclusi disponibilità effettiva al cutoff e distinzione tra run operativi e hindcast. Consultare `reports/weather/forecast_feasibility.md`. Nessun file di forecast è stato creato o completato usando ERA5.

Fonte: Open-Meteo Historical Weather API, ERA5 (ECMWF/Copernicus). Link e condizioni di attribuzione sono indicati nel notebook e nel report.
