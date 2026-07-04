
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

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

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
    price     = to_float(row.get("price"))
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
        "OPEN": price,
        "HIGH": price,
        "LOW": price,
        "CLOSE": price,
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

@app.get("/health")
def health():
    return {"status": "ok", "gemini": bool(GEMINI_KEY)}

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
    """Generate AI research report using Gemini — runs on Railway, no CPU timeout"""
    if not GEMINI_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not set in Railway environment")

    symbol    = body.get("symbol", "UNKNOWN")
    price     = body.get("price", 0)
    change_pct = body.get("changePct", 0)
    rsi       = body.get("rsi", "N/A")
    pe        = body.get("pe", "N/A")

    prompt = f"""You are a PSX (Pakistan Stock Exchange) equity analyst.
Analyse {symbol} at Rs {price} ({change_pct}% today, RSI: {rsi}, P/E: {pe}).
Pakistan market context: KSE-100, PKR currency.

Reply ONLY with JSON (no markdown):
{{"recommendation":"buy","confidence":65,"summary":"2-3 sentence summary.","technical_notes":"Technical note.","fundamental_notes":"Fundamental note.","news_impact":"Pakistan macro context.","bull_case":"Bull scenario.","bear_case":"Bear scenario.","entry_price":{price},"stop_loss":{round(price*0.95,2)},"target_1":{round(price*1.08,2)},"target_2":{round(price*1.15,2)},"risk_level":"medium"}}"""

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 600}
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
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                clean = text.replace("```json","").replace("```","").strip()
                report = json.loads(clean)
                report["_model"] = model
                return report
        except urllib.error.HTTPError as e:
            last_error = f"{model}: HTTP {e.code}"
            if e.code in (429, 503):
                continue  # try next model
            break
        except Exception as e:
            last_error = f"{model}: {str(e)}"
            continue

    # All models failed — return basic report
    return {
        "recommendation": "hold",
        "confidence": 45,
        "summary": f"AI analysis temporarily unavailable for {symbol}. Please retry in a few minutes.",
        "technical_notes": f"{symbol} at Rs {price}, change: {change_pct}%.",
        "fundamental_notes": f"P/E: {pe}" if pe != "N/A" else "Data unavailable.",
        "news_impact": "Pakistan market analysis unavailable.",
        "bull_case": "Retry for full analysis.",
        "bear_case": "Retry for full analysis.",
        "entry_price": price,
        "stop_loss": round(price * 0.95, 2),
        "target_1": round(price * 1.08, 2),
        "target_2": round(price * 1.15, 2),
        "risk_level": "medium",
        "_error": last_error,
    }


@app.get("/test-gemini")
def test_gemini():
    """Test Gemini connection directly"""
    if not GEMINI_KEY:
        return {"error": "No key set"}
    
    errors = {}
    for model in MODELS:
        try:
            payload = json.dumps({
                "contents": [{"parts": [{"text": "Say hello in one word"}]}],
                "generationConfig": {"maxOutputTokens": 10}
            }).encode()
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return {"success": True, "model": model, "response": text}
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            errors[model] = f"HTTP {e.code}: {body[:200]}"
        except Exception as e:
            errors[model] = str(e)
    
    return {"success": False, "errors": errors}
