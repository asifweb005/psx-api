from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psxdata
import os
import json
import re
import urllib.request
import urllib.error

app = FastAPI(title="PSX Data & AI API", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

def to_float(v):
    try: return float(v) if v is not None else 0.0
    except: return 0.0

def to_int(v):
    try: return int(str(v).replace(",","")) if v is not None else 0
    except: return 0

SECTOR_NAMES = {
    "807":"Commercial Banks","806":"Insurance",
    "820":"Oil & Gas Exploration","821":"Oil & Gas Marketing",
    "804":"Cement","809":"Fertilizer","824":"Power Generation",
    "828":"Technology & Communication","823":"Pharmaceuticals",
    "810":"Food & Personal Care","801":"Automobile Assembler",
    "805":"Chemical","832":"Tobacco","838":"Miscellaneous",
}

def sector_name(code):
    key = str(code).replace(".0","").strip()
    return SECTOR_NAMES.get(key, key)

def quote_to_stock(sym, df):
    if df is None or len(df) == 0:
        return None
    row = df.iloc[0].to_dict()
    price = to_float(row.get("price"))
    change_pct = to_float(row.get("change_pct"))
    if change_pct != 0:
        ldcp = price / (1 + change_pct / 100)
        change = price - ldcp
    else:
        ldcp = price
        change = 0.0
    return {
        "SYMBOL": sym,
        "COMPANY": str(row.get("company") or sym),
        "SECTOR": sector_name(row.get("sector","")),
        "LDCP": round(ldcp, 2),
        "OPEN": price, "HIGH": price, "LOW": price, "CLOSE": price,
        "VOLUME": to_int(row.get("volume_avg_30d")),
        "CHANGE": round(change, 2),
        "CHANGE%": change_pct,
        "PE_RATIO": to_float(row.get("pe_ratio")),
        "DIVIDEND_YIELD": to_float(row.get("dividend_yield")),
    }

TOP_STOCKS = [
    "HBL","UBL","MCB","ABL","BAFL","BAHL","MEBL","JSBL",
    "OGDC","PPL","MARI","POL","PARCO",
    "ENGRO","EFERT","FATIMA","FFC","FFBL",
    "LUCK","DGKC","FCCL","KOHC","PIOC","CHCC",
    "HUBC","KAPCO","KEL","NCPL",
    "PSO","APL","SHEL",
    "TRG","SYS","NETSOL","AVN","TPLP",
    "SEARL","ABOT","HINOON","GLAXO","FEROZ",
    "PSMC","INDU","HCAR","SAZEW",
    "NESTLE","UNITY","TREET",
    "PAKT","LOTCHEM","ICI","SITC",
]

def extract_gemini_text(data):
    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("No candidates")
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts:
        finish = candidates[0].get("finishReason", "unknown")
        raise ValueError("No parts, finishReason: " + finish)
    return parts[0].get("text", "")

def call_gemini(prompt):
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800}
    }).encode()

    last_error = ""
    for model in MODELS:
        try:
            url = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   + model + ":generateContent?key=" + GEMINI_KEY)
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
                text = extract_gemini_text(data)
                if text:
                    return text
                last_error = model + ": empty text"
        except urllib.error.HTTPError as e:
            e.read()
            last_error = model + ": HTTP " + str(e.code)
            if e.code in (429, 503, 404):
                continue
        except Exception as e:
            last_error = model + ": " + str(e)
            continue

    raise ValueError("All models failed. Last: " + last_error)

def parse_json_from_text(text):
    """Extract and parse JSON from Gemini response — handles markdown fences and extra text"""
    # Remove markdown fences
    text = text.replace("```json", "").replace("```", "").strip()
    # Find the outermost JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        candidate = text[start:end]
        return json.loads(candidate)
    raise ValueError("No JSON object found in response")

def fallback_report(symbol, price, change_pct, rsi, pe):
    stop_loss = round(price * 0.95, 2)
    target_1  = round(price * 1.08, 2)
    target_2  = round(price * 1.15, 2)
    return {
        "recommendation": "hold",
        "confidence": 45,
        "summary": symbol + " is trading at Rs " + str(price) + " with " + str(change_pct) + "% change. Full AI analysis temporarily unavailable — please retry.",
        "technical_notes": "Price: Rs " + str(price) + " | Change: " + str(change_pct) + "% | RSI: " + str(rsi),
        "fundamental_notes": "P/E ratio: " + str(pe),
        "news_impact": "Pakistan market analysis unavailable. Please retry.",
        "bull_case": "Retry for detailed bull case.",
        "bear_case": "Retry for detailed bear case.",
        "entry_price": price,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "risk_level": "medium",
    }

@app.get("/health")
def health():
    return {"status": "ok", "gemini": bool(GEMINI_KEY)}

@app.get("/test-gemini")
def test_gemini():
    if not GEMINI_KEY:
        return {"error": "No key"}
    try:
        text = call_gemini("Say hello in one word only.")
        return {"success": True, "response": text.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/market-watch")
def market_watch():
    result = []
    for sym in TOP_STOCKS:
        try:
            df = psxdata.quote(sym)
            stock = quote_to_stock(sym, df)
            if stock and stock["CLOSE"] > 0:
                result.append(stock)
        except:
            continue
    if not result:
        raise HTTPException(status_code=500, detail="No data fetched")
    return result

@app.get("/quote/{symbol}")
def quote_endpoint(symbol: str):
    try:
        df = psxdata.quote(symbol.upper())
        stock = quote_to_stock(symbol.upper(), df)
        if not stock:
            raise HTTPException(status_code=404, detail="Not found")
        return stock
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/history/{symbol}")
def history(symbol: str):
    try:
        from datetime import datetime, timedelta
        end = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
        df = psxdata.stocks(symbol.upper(), start=start, end=end)
        if hasattr(df, "reset_index"):
            records = df.reset_index().to_dict(orient="records")
            return [{str(k): (v.isoformat() if hasattr(v,"isoformat") else v)
                     for k,v in r.items()} for r in records]
        return []
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/research")
def research(body: dict):
    # Always return 200 — never 500 — so the app always shows something
    if not GEMINI_KEY:
        return fallback_report("UNKNOWN", 0, 0, "N/A", "N/A")

    symbol     = str(body.get("symbol", "UNKNOWN"))
    price      = float(body.get("price", 0))
    change_pct = float(body.get("changePct", 0))
    rsi        = str(body.get("rsi", "N/A"))
    pe         = str(body.get("pe", "N/A"))
    stop_loss  = round(price * 0.95, 2)
    target_1   = round(price * 1.08, 2)
    target_2   = round(price * 1.15, 2)

    prompt = (
        "You are a PSX (Pakistan Stock Exchange) equity analyst.\n"
        "Stock: " + symbol + "\n"
        "Current price: Rs " + str(price) + "\n"
        "Change today: " + str(change_pct) + "%\n"
        "RSI-14: " + rsi + "\n"
        "P/E ratio: " + pe + "\n"
        "Market: KSE-100, Pakistan, PKR currency\n\n"
        "IMPORTANT: Respond with ONLY a valid JSON object. No text before or after. No markdown fences.\n"
        "Required JSON structure:\n"
        '{"recommendation":"buy","confidence":70,'
        '"summary":"Your 2-3 sentence summary here.",'
        '"technical_notes":"Your technical analysis here.",'
        '"fundamental_notes":"Your fundamental analysis here.",'
        '"news_impact":"Pakistan macro and sector context here.",'
        '"bull_case":"Your bull case scenario here.",'
        '"bear_case":"Your bear case scenario here.",'
        '"entry_price":' + str(price) + ","
        '"stop_loss":' + str(stop_loss) + ","
        '"target_1":' + str(target_1) + ","
        '"target_2":' + str(target_2) + ","
        '"risk_level":"medium"}'
    )

    try:
        text = call_gemini(prompt)
        report = parse_json_from_text(text)
        # Ensure required fields exist
        report.setdefault("recommendation", "hold")
        report.setdefault("confidence", 50)
        report.setdefault("entry_price", price)
        report.setdefault("stop_loss", stop_loss)
        report.setdefault("target_1", target_1)
        report.setdefault("target_2", target_2)
        report.setdefault("risk_level", "medium")
        return report
    except Exception as e:
        # Log error but always return 200 with fallback
        print("Research error:", str(e))
        return fallback_report(symbol, price, change_pct, rsi, pe)
