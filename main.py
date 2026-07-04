from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psxdata
import os
import json
import urllib.request
import urllib.error

app = FastAPI(title="PSX Data & AI API", version="2.0.0")

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

def extract_gemini_text(data: dict) -> str:
    """Safely extract text from Gemini response — handles all response shapes"""
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates in response")
        candidate = candidates[0]
        
        # Handle finish reason without content (e.g. safety block)
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        if not parts:
            # Some models return text directly
            finish = candidate.get("finishReason", "")
            raise ValueError(f"No parts in response, finishReason: {finish}")
        
        return parts[0].get("text", "")
    except Exception as e:
        raise ValueError(f"Could not extract text: {e}, raw: {str(data)[:300]}")

def call_gemini(prompt: str) -> str:
    """Call Gemini API, trying models in order. Returns text or raises."""
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 800,
        }
    }).encode()

    last_error = ""
    for model in MODELS:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
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
                last_error = f"{model}: empty text"
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            last_error = f"{model}: HTTP {e.code}"
            if e.code in (429, 503):
                continue
            if e.code == 404:
                continue
            raise ValueError(f"Gemini error {e.code}: {body[:200]}")
        except ValueError as e:
            last_error = f"{model}: {e}"
            continue
        except Exception as e:
            last_error = f"{model}: {e}"
            continue

    raise ValueError(f"All models failed. Last: {last_error}")

@app.get("/health")
def health():
    return {"status": "ok", "gemini": bool(GEMINI_KEY)}

@app.get("/test-gemini")
def test_gemini():
    if not GEMINI_KEY:
        return {"error": "No key set"}
    try:
        text = call_gemini("Say hello in exactly one word. No punctuation.")
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
        if hasattr(df, 'reset_index'):
            records = df.reset_index().to_dict(orient="records")
            return [{str(k): (v.isoformat() if hasattr(v,'isoformat') else v)
                     for k,v in r.items()} for r in records]
        return []
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/research")
def research(body: dict):
    if not GEMINI_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not set")

    symbol     = body.get("symbol", "UNKNOWN")
    price      = body.get("price", 0)
    change_pct = body.get("changePct", 0)
    rsi        = body.get("rsi", "N/A")
    pe         = body.get("pe", "N/A")

    prompt = f"""You are a PSX (Pakistan Stock Exchange) equity analyst.
Analyse {symbol} at Rs {price} ({change_pct}% today, RSI: {rsi}, P/E: {pe}).
Pakistan market context: KSE-100 index, PKR currency, interest rates, inflation.

You MUST respond with ONLY a valid JSON object. No markdown. No explanation. No backticks.
Use exactly these keys:
{{
  "recommendation": "buy",
  "confidence": 65,
  "summary": "2-3 sentence executive summary of the stock.",
  "technical_notes": "Technical analysis based on price and RSI.",
  "fundamental_notes": "Fundamental analysis based on P/E and sector.",
  "news_impact": "Pakistan macro and sector context.",
  "bull_case": "Bull case scenario with upside catalyst.",
  "bear_case": "Bear case scenario with downside risk.",
  "entry_price": {price},
  "stop_loss": {round(price * 0.95, 2)},
  "target_1": {round(price * 1.08, 2)},
  "target_2": {round(price * 1.15, 2)},
  "risk_level": "medium"
}}"""

    try:
        text = call_gemini(prompt)
        clean = text.replace("```json", "").replace("```", "").strip()
        # Find JSON object in response
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start >= 0 and end > start:
            clean = clean[start:end]
        report = json.loads(clean)
        return report
    except json.JSONDecodeError as e:
        # Return basic report if JSON parsing fails
        return {
            "recommendation": "hold",
            "confidence": 45,
            "summary": f"Analysis generated for {symbol} at Rs {price}. JSON parsing issue - please retry.",
            "technical_notes": f"Price: Rs {price}, Change: {change_pct}%, RSI: {rsi}",
            "fundamental_notes": f"P/E ratio: {pe}",
            "news_impact": "Pakistan market data available.",
            "bull_case": "Please retry for detailed analysis.",
            "bear_case": "Please retry for detailed analysis.",
            "entry_price": price,
            "stop_loss": round(price * 0.95, 2),
            "target_1": round(price * 1.08, 2),
            "target_2": round(price * 1.15, 2),
            "risk_level": "medium",
            "_parse_error": str(e),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
