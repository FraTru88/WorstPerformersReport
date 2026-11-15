"""
Weekly Worst Performers Report
- Top 10 peggiori per ogni indice presente su Firestore (FTSE MIB, FTSE STAR, ...)
- Gli indici sono letti dalla collection "benchmarks", un documento per indice:
    name:    "FTSE_MIB"          
    tickers: ["A2A.MI", ...]     (array di string, vedi carica_mercati.py)
    color:   "#009246"           (opzionale: colore della tabella, default nero)
    active:  true                (opzionale, default true: false = indice saltato nel report)
Invia un'email con i risultati.

Dipendenze:
    pip install yfinance pandas python-dotenv firebase-admin

Variabili d'ambiente (.env in locale, GitHub Secrets su Actions):
    EMAIL_MITTENTE, EMAIL_DESTINATARIO, GMAIL_APP_PASSWORD
    FIREBASE_CREDENTIALS=serviceAccount.json
    FIREBASE_CREDENTIALS_JSON={...contenuto del JSON...}   (alternativa, per CI)
"""

import html
import logging
import math
import os
import re
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from firestore_client import init_firestore, get_collection, close_firestore
from email_client import send_email

load_dotenv()

# ─── CONFIGURAZIONE ──────────────────────────────────────────────────────────
EMAIL_MITTENTE = os.getenv("EMAIL_MITTENTE")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")  # Da GitHub Secrets

COLLECTION = "benchmarks"
TOP_N = 10
GIORNI_FINESTRA = 7      # confronto tra ultima chiusura e chiusura di 7 giorni prima
MAX_GIORNI_STALE = 3     # scarta ticker il cui ultimo prezzo e' piu' vecchio del resto del mercato

COLORE_DEFAULT = "#000000"
RE_COLORE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")  # es. #009246 oppure #0a4

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _attivo(valore) -> bool:
    """active mancante o null = attivo. Salta solo se e' false (accetta anche la stringa "false")."""
    if valore is None:
        return True
    if isinstance(valore, str):
        return valore.strip().lower() not in ("false", "0", "no", "off")
    return bool(valore)


def carica_benchmarks(db) -> list[dict]:
    """Legge tutti i documenti di "benchmarks": id, titolo, colore e ticker di ogni indice attivo."""
    benchmarks = []
    for ref, d in get_collection(db, COLLECTION):
        if not _attivo(d.get("active")):
            log.info("%s: active=false, saltato", ref.id)
            continue

        tickers = list(dict.fromkeys(
            t.strip().upper() for t in d.get("tickers", []) if t and t.strip()
        ))
        if not tickers:
            log.warning("%s: campo 'tickers' vuoto o mancante, saltato", ref.id)
            continue

        colore = str(d.get("color") or "").strip()
        if not RE_COLORE.fullmatch(colore):
            if colore:
                log.warning("%s: colore '%s' non valido (atteso es. #009246), uso il nero", ref.id, colore)
            colore = COLORE_DEFAULT

        log.info("%s: %d ticker letti da Firestore", ref.id, len(tickers))
        benchmarks.append({
            "id": ref.id,
            "label": str(d.get("name") or ref.id).replace("_", " "),
            "color": colore,
            "tickers": tickers,
        })
    return sorted(benchmarks, key=lambda x: x["id"])


# ─── DATI ────────────────────────────────────────────────────────────────────
def get_weekly_performance(tickers: list[str], index_name: str, top: int = TOP_N) -> pd.DataFrame:
    """Variazione % tra l'ultima chiusura e quella di GIORNI_FINESTRA giorni prima; restituisce i `top` peggiori."""
    oggi = datetime.today()
    log.info("Scarico dati per %s...", index_name)
    # end e' ESCLUSIVO in yfinance: +1 giorno per includere la chiusura di oggi (venerdi')
    data = yf.download(
        tickers,
        start=oggi - timedelta(days=GIORNI_FINESTRA + 7),
        end=oggi + timedelta(days=1),
        progress=False,
        auto_adjust=True,
    )
    if data.empty:
        log.warning("Nessun dato disponibile per %s", index_name)
        return pd.DataFrame()

    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    ultima_data_mercato = close.index.max()

    performance, senza_dati, stale = {}, [], []
    for ticker in close.columns:
        prezzi = close[ticker].dropna()
        if prezzi.empty:
            senza_dati.append(ticker)
            continue
        ultimo_giorno = prezzi.index[-1]
        if (ultima_data_mercato - ultimo_giorno).days > MAX_GIORNI_STALE:
            stale.append(ticker)
            continue
        base = prezzi[prezzi.index <= ultimo_giorno - timedelta(days=GIORNI_FINESTRA)]
        if base.empty:
            senza_dati.append(ticker)
            continue
        performance[ticker] = round((prezzi.iloc[-1] / base.iloc[-1] - 1) * 100, 2)

    mancanti = sorted(set(tickers) - set(close.columns)) + senza_dati
    if mancanti:
        log.warning("%s: nessun dato utile per %s", index_name, mancanti)
    if stale:
        log.warning("%s: prezzo non aggiornato (sospesi/delistati?) per %s", index_name, stale)

    df = pd.DataFrame.from_dict(performance, orient="index", columns=["Variazione %"])
    df.index.name = "Ticker"
    return df.sort_values("Variazione %", ascending=True).head(top)


def _to_float(valore):
    """yfinance a volte restituisce None, stringhe ('Infinity') o NaN al posto del P/E."""
    try:
        f = float(valore)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def aggiungi_dettagli(df: pd.DataFrame) -> pd.DataFrame:
    """Nome e P/E forward, scaricati solo per i titoli finiti nel report (non per tutto l'indice)."""
    nomi, pe = [], []
    for ticker in df.index:
        try:
            info = yf.Ticker(ticker).info
        except Exception as e:
            log.warning("Info non disponibili per %s: %s", ticker, e)
            info = {}
        nomi.append(info.get("shortName") or info.get("longName") or ticker)
        pe.append(_to_float(info.get("forwardPE")))
    df = df.copy()
    df["Nome"] = nomi
    df["P/E"] = pe
    return df


# ─── HTML / EMAIL ────────────────────────────────────────────────────────────
def build_html_table(df: pd.DataFrame, index_name: str, color: str) -> str:
    """Crea una tabella HTML con Variazione % e P/E."""
    rows = ""
    for i, (ticker, row) in enumerate(df.iterrows(), 1):
        perf = row["Variazione %"]
        perf_str = f"{perf:+.2f}%" if pd.notnull(perf) else "N/D"
        pe = row["P/E"]
        pe_str = f"{pe:.2f}" if pd.notnull(pe) else "N/D"
        name = html.escape(str(row["Nome"]))

        bg = "#fff0f0" if i % 2 == 0 else "#ffffff"
        rows += f"""
        <tr style="background:{bg}">
            <td style="padding:8px 12px; font-weight:bold; color:#555;">{i}</td>
            <td style="padding:8px 12px; font-weight:bold;">{html.escape(ticker)}</td>
            <td style="padding:8px 12px; font-weight:bold;">{name}</td>
            <td style="padding:8px 12px; color:#cc0000; font-weight:bold; text-align:right;">{perf_str}</td>
            <td style="padding:8px 12px; text-align:right;">{pe_str}</td>
        </tr>"""

    return f"""
    <div style="margin-bottom:30px;">
        <h2 style="color:{color}; border-left:4px solid {color}; padding-left:10px;">
            📉 {html.escape(index_name)} — Top {len(df)} Peggiori della Settimana
        </h2>
        <table style="width:100%; border-collapse:collapse; font-family:Arial,sans-serif; font-size:14px;">
            <thead>
                <tr style="background:{color}; color:white;">
                    <th style="padding:10px 12px; text-align:left;">#</th>
                    <th style="padding:10px 12px; text-align:left;">Ticker</th>
                    <th style="padding:10px 12px; text-align:left;">Name</th>
                    <th style="padding:10px 12px; text-align:right;">Variazione</th>
                    <th style="padding:10px 12px; text-align:right;">P/E (forward)</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


def send_email_full(html_content: str):
    """Invia l'email tramite Gmail SMTP."""    
    today = datetime.today().strftime("%d/%m/%Y")
    subject = f"📉 Report Settimanale Peggiori Performer — {today}"
    html_full = f"""
    <html><body style="font-family:Arial,sans-serif; max-width:700px; margin:auto; padding:20px; color:#333;">
        <h1 style="text-align:center; color:#222;">📊 Report Settimanale</h1>
        <p style="text-align:center; color:#888;">Settimana terminante il {today}</p>
        <hr style="border:none; border-top:1px solid #ddd; margin:20px 0;">
        {html_content}
        <hr style="border:none; border-top:1px solid #ddd; margin:20px 0;">
        <p style="font-size:12px; color:#aaa; text-align:center;">
            Report generato automaticamente via GitHub Actions + yfinance.<br>
            I dati sono puramente informativi e non costituiscono consulenza finanziaria.
        </p>
    </body></html>
    """
    send_email(subject,html_full)


# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    mancanti = [
        nome for nome, v in (
            ("EMAIL_MITTENTE", EMAIL_MITTENTE),
            ("EMAIL_DESTINATARIO", EMAIL_DESTINATARIO),
            ("GMAIL_APP_PASSWORD", GMAIL_APP_PASSWORD),
        ) if not v
    ]
    if mancanti:  # meglio fallire subito che dopo decine di download
        raise RuntimeError(f"Variabili d'ambiente mancanti: {mancanti}")

    db = init_firestore()

    try:
        html_tables = ""
        for bm in carica_benchmarks(db):
            df = get_weekly_performance(bm["tickers"], bm["label"])
            if df.empty:
                continue
            html_tables += build_html_table(aggiungi_dettagli(df), bm["label"], bm["color"])

        if html_tables:
            send_email_full(html_tables)
        else:
            log.error("❌ Nessun dato disponibile. Email non inviata.")
    finally:
        close_firestore()


if __name__ == "__main__":
    main()