# Previsioni meteo archiviate: verifica preliminare

**Esito: il dataset day-ahead finale non è ancora pronto.** L'estrazione esplorativa ERA5 2022–2025 è stata completata e verificata; non si può certificare una copertura forecast omogenea dell'intero periodo con le sole informazioni finora verificate. Verifica documentale: 1 novembre 2026. Copertura effettiva delle API forecast non ancora verificata. Il download Historical Weather è invece riuscito tramite Colab; i suoi dati sono allegati e verificati.

| Prodotto Open-Meteo | Natura | Conseguenza per il progetto |
| --- | --- | --- |
| Historical Weather, ERA5 | Rianalisi a posteriori | Adatta a esplorazione; non prova la disponibilità al cutoff day-ahead |
| Historical Forecast | Serie che concatena le prime ore di run successivi, con storia variabile per modello | La denominazione «forecast» non basta a ricostruire una previsione disponibile il giorno prima |
| Previous Runs | Serie a scadenza fissa di 1–7 giorni; generalmente da gennaio 2024, con eccezioni | Utile da approfondire; non è automaticamente una previsione unica per tutte le ore del giorno successivo |
| Single Runs | Run distinti per inizializzazione | Struttura più vicina alla necessità del progetto, da verificare per periodo e natura dell'archivio |

La documentazione delle Single Runs dichiara ECMWF IFS dal **14 marzo 2024**, ma specifica **IFS Cycle 49R1 hindcasts** per parte dell'archivio. Gli altri modelli sono indicati dal **2 aprile 2026**, fuori dall'intervallo 2022–2025. La presenza di hindcast richiede una verifica ulteriore: non va assimilata automaticamente al forecast operativo davvero pubblicato in quella data. L'inizializzazione del run non coincide inoltre con il momento di disponibilità pubblica.

La documentazione Previous Runs segnala storia più lunga per la temperatura GFS (da marzo 2021) e per alcuni modelli JMA (dal 2018). Questo **non verifica** la copertura di tutte e tre le variabili nelle sei città per l'intero intervallo: vanno interrogate e controllate singolarmente.

## Decisioni da concordare con il gruppo prima della costruzione forecast finale

1. **Cutoff della previsione elettrica:** quale ora del giorno precedente, e in quale fuso? Non assumere mezzanotte o un'ora non indicata.
2. **Autenticità dell'archivio:** run operativi originari oppure hindcast ricostruiti? Per un backtest rigoroso verificare la fonte con Open-Meteo se la documentazione non basta.
3. **Disponibilità:** scegliere solo run effettivamente pubblicati entro il cutoff. Un semplice `run_time_utc <= cutoff` è insufficiente.
4. **Copertura:** verificare tutte le variabili, i modelli e le sei città. Se il periodo completo non è disponibile, documentare i vuoti o concordare un intervallo minore; mai riempire con ERA5.

Queste verifiche restano necessarie anche se un'API risponde senza errori.

## Schema previsto, da finalizzare

File distinto: `weather_forecast_clean.csv`, in formato lungo.

| Colonna | Significato |
| --- | --- |
| `issue_time_utc` | Emissione del forecast, con definizione documentata |
| `run_time_utc` | Inizializzazione del modello |
| `available_time_utc` | Prima disponibilità pubblica, oppure stima esplicita e giustificata |
| `target_time_utc` | Ora futura cui si riferisce il valore |
| `city` | Città |
| `model` | Modello, versione quando disponibile |
| `source_kind` | Forecast operativo oppure hindcast, tenuti distinti |
| `temp_c`, `humidity_pct`, `cloud_cover_pct` | Variabili previste |

Non inventare `issue_time_utc` sottraendo 24 ore a `target_time_utc`. Non confondere inizializzazione, emissione e disponibilità. Definire la chiave sulla base di modello/run/città/target; selezionare il run con una regola unica documentata. Validare il giorno target in `Europe/Rome`, incluse le giornate di 23/25 ore.

## Fonti ufficiali

- https://open-meteo.com/en/docs/historical-weather-api
- https://open-meteo.com/en/docs/historical-forecast-api
- https://open-meteo.com/en/docs/previous-runs-api
- https://open-meteo.com/en/docs/single-runs-api
- https://open-meteo.com/en/docs/model-updates

La scelta di non certificare ancora il backtest è una valutazione metodologica basata su queste limitazioni, non una dichiarazione che qualsiasi archivio operativo alternativo sia indisponibile.
