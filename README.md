# 📉 Weekly Worst Performers Report

Script che invia automaticamente via email le **Top 10 aziende che hanno performato peggio** nella settimana per ciascun indice configurato, ad esempio:
- 🇮🇹 **FTSE MIB**
- 🇮🇹 **FTSE STAR**

Per ogni titolo il report mostra ticker, nome, variazione % e P/E forward.

Giorno e orario di invio **li decide l'utente**, configurandoli sul cronjob esterno che avvia lo script (vedi [Avvio automatico](#-avvio-automatico)).

Gli indici e le liste di ticker **non sono nel codice**: sono salvati su **Firebase (Firestore)**, nella collection `benchmarks`. Per aggiungere, togliere o ricolorare un indice basta modificare il database, senza toccare lo script.

---

## ⚙️ Configurazione

### 1. Genera una Gmail App Password
> Necessario perché Gmail non accetta la password normale per accessi via script.

1. Vai su [myaccount.google.com](https://myaccount.google.com)
2. **Sicurezza** → **Verifica in due passaggi** (deve essere attiva)
3. **Sicurezza** → **Password per le app**
4. Seleziona "Posta" e "Computer Windows/Mac/Linux"
5. Copia la password generata 

### 2. Crea la chiave del service account Firebase
> Serve allo script per leggere gli indici da Firestore.

1. Nella [console Firebase](https://console.firebase.google.com) apri il progetto → **Impostazioni progetto** → **Account di servizio**
2. Clicca **Genera nuova chiave privata** e scarica il file JSON
3. **Non committarlo mai nel repository** (aggiungilo al `.gitignore`): chi lo possiede ha accesso al database

### 3. Aggiungi i Secret su GitHub
Nel tuo repository GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**. Crea questi quattro secret:

| Nome | Valore |
|---|---|
| `GMAIL_APP_PASSWORD` | la App Password del punto 1, senza spazi |
| `EMAIL_MITTENTE` | la tua email Gmail |
| `EMAIL_DESTINATARIO` | l'indirizzo dove vuoi ricevere il report |
| `FIREBASE_CREDENTIALS_JSON` | l'**intero contenuto** del file JSON del punto 2 |

### 4. Carica gli indici su Firestore
Gli indici stanno nella collection `benchmarks`, un documento per indice:

| Campo | Tipo | Descrizione |
|---|---|---|
| `name` | string | Titolo nel report, es. `FTSE_MIB` (gli `_` diventano spazi) |
| `tickers` | array di string | Ticker Yahoo Finance, es. `["A2A.MI", "ENEL.MI"]` |
| `color` | string, opzionale | Colore della tabella, es. `#009246`. Se manca o non è valido: nero |
| `active` | boolean, opzionale | `false` = indice saltato nel report. Se manca vale `true` |

L'ID del documento coincide con `name`, quindi rilanciare lo script **aggiorna** i documenti invece di duplicarli. Aggiorna solo `name`, `tickers`, `count` e `updated_at`: i campi che aggiungi a mano (`color`, `active`) restano intatti.

Dopo il primo caricamento, aggiungi `color` ai documenti dalla console Firebase e, per escludere un indice (ad esempio `SP_500`), imposta `active` a `false` come **boolean**.

### 5. Carica tutto su GitHub e sei pronto!
Il workflow parte quando viene avviato dal cronjob esterno (vedi sotto). Giorno e orario li scegli tu.

---

## ⏰ Avvio automatico

L'avvio periodico è affidato a un **cronjob esterno** e non allo `schedule` di GitHub Actions, perché l'esecuzione dei job schedulati di GitHub non è affidabile (possono partire in ritardo o non partire affatto).

Il cronjob avvia il workflow chiamando l'API di GitHub, grazie al trigger `workflow_dispatch`:

```
POST /repos/<utente>/<repo>/actions/workflows/<file>.yml/dispatches
```

con un token che abbia il permesso *Actions: write*.

**Giorno e orario di invio sono decisi dall'utente**, impostandoli nel servizio di cron scelto.

> ⚠️ Consiglio: lancia il report dopo la chiusura dell'ultimo mercato incluso, altrimenti i dati della giornata sono parziali o mancano.
> Borsa Italiana chiude alle 17:30 e Wall Street alle 22:00 (ora italiana).

---

## 🧪 Test manuale
Puoi avviarlo subito, senza aspettare il prossimo invio programmato:
1. Vai nel tuo repository → **Actions**
2. Seleziona **Weekly Worst Performers Report**
3. Clicca **Run workflow** → **Run workflow**

In locale, con un file `.env` contenente le quattro variabili (`GMAIL_APP_PASSWORD`, `EMAIL_MITTENTE`, `EMAIL_DESTINATARIO` e `FIREBASE_CREDENTIALS` col percorso del JSON):

```bash
python weekly_worst_performers.py
```

---

## 📦 Dipendenze
- `yfinance` — dati di borsa
- `pandas` — elaborazione dati
- `firebase-admin` — lettura degli indici da Firestore
- `python-dotenv` — caricamento del file `.env` in locale
- `smtplib` — invio email (incluso in Python)

```bash
pip install yfinance pandas python-dotenv firebase-admin
```

---

## ⚠️ Note
- I dati provengono da Yahoo Finance e potrebbero avere piccoli ritardi o errori.
- La variazione è calcolata tra l'ultima chiusura disponibile e quella di 7 giorni prima. I titoli sospesi o delistati vengono scartati.
- Il P/E è quello **forward** fornito da Yahoo: per alcuni titoli può mancare (`N/D`).
- Il report è puramente informativo e non costituisce consulenza finanziaria.
