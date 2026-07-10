from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psxdata
import os
import json
import math
import urllib.request
import urllib.error
from datetime import datetime, timedelta

app = FastAPI(title="PSX Data & AI API", version="5.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_KEY   = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

GROQ_MODELS   = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]

def safe_float(v, default=0.0):
    try:
        f = float(v) if v is not None else default
        return default if (math.isnan(f) or math.isinf(f)) else f
    except:
        return default

def safe_int(v, default=0):
    try:
        return int(str(v).replace(",","")) if v is not None else default
    except:
        return default

def sanitize(obj):
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, float):
        return 0.0 if (math.isnan(obj) or math.isinf(obj)) else obj
    return obj

SECTOR_NAMES = {
    "807":"Commercial Banks","806":"Insurance",
    "820":"Oil & Gas Exploration","821":"Oil & Gas Marketing",
    "804":"Cement","809":"Fertilizer","824":"Power Generation",
    "828":"Technology & Communication","823":"Pharmaceuticals",
    "810":"Food & Personal Care","801":"Automobile Assembler",
    "805":"Chemical","832":"Tobacco","838":"Miscellaneous",
    "803":"Sugar & Allied","816":"Textile Composite",
    "817":"Textile Spinning","818":"Textile Weaving",
    "826":"Paper & Board","827":"Engineering",
    "808":"Engineering","813":"Leatherware",
    "825":"Refinery","829":"Textile","830":"Glass & Ceramics",
    "833":"Transport","802":"Automobile Parts",
}

def sector_name(code):
    key = str(code).replace(".0","").strip()
    return SECTOR_NAMES.get(key, key)

def quote_row_to_stock(sym, row, include_ohlcv=False):
    """Convert a psxdata quote row to our standard format.
    include_ohlcv=True fetches real OHLCV from history (slow, only for detail view).
    """
    price      = safe_float(row.get("price"))
    change_pct = safe_float(row.get("change_pct"))
    if change_pct != 0:
        ldcp   = price / (1 + change_pct / 100)
        change = price - ldcp
    else:
        ldcp   = price
        change = 0.0

    open_  = price
    high   = price
    low    = price
    volume = safe_int(row.get("volume_avg_30d"))

    if include_ohlcv:
        try:
            end   = datetime.today().strftime("%Y-%m-%d")
            start = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")
            df = psxdata.stocks(sym, start=start, end=end)
            if df is not None and len(df) > 0:
                last = df.iloc[-1].to_dict()
                open_  = safe_float(last.get("Open")   or last.get("open"),   price)
                high   = safe_float(last.get("High")   or last.get("high"),   price)
                low    = safe_float(last.get("Low")    or last.get("low"),    price)
                volume = safe_int(  last.get("Volume") or last.get("volume"))
        except:
            pass

    return sanitize({
        "SYMBOL":         sym,
        "COMPANY":        str(row.get("company") or sym),
        "SECTOR":         sector_name(row.get("sector", "")),
        "LDCP":           round(ldcp, 2),
        "OPEN":           open_,
        "HIGH":           high,
        "LOW":            low,
        "CLOSE":          price,
        "VOLUME":         volume,
        "CHANGE":         round(change, 2),
        "CHANGE%":        change_pct,
        "PE_RATIO":       safe_float(row.get("pe_ratio")),
        "DIVIDEND_YIELD": safe_float(row.get("dividend_yield")),
        "MARKET_CAP":     safe_float(row.get("market_cap")),
        "LISTED_IN":      str(row.get("listed_in") or ""),
    })

TOP_STOCKS = [
    "HBL","UBL","MCB","ABL","BAFL","BAHL","MEBL","JSBL","NBP",
    "AKBL","SNBL","BOP","FAYSAL","SCBPL","PIBTL",
    "OGDC","PPL","MARI","POL","PSO","APL","SHEL",
    "SNGP","SSGC","PARCO","BYCO","HASCOL","ATRL",
    "ENGRO","EFERT","FATIMA","FFC","FFBL",
    "LUCK","DGKC","FCCL","KOHC","PIOC","CHCC","MLCF","GWLC",
    "BWCL","JVDC","THCCL","FLYNG","LPCL",
    "HUBC","KAPCO","KEL","NCPL","PKGP","JPGL","TSPL",
    "TRG","SYS","NETSOL","AVN","TPLP","PSEL","HUMNL",
    "SEARL","ABOT","HINOON","GLAXO","FEROZ","SAPL","AGP",
    "PSMC","INDU","HCAR","SAZEW","MTL","GHNL",
    "NESTLE","UNITY","TREET","QUICE","ISIL",
    "NCL","KTML","NML","RCML","ADMM","GATM","SHFA",
    "LOTCHEM","ICI","SITC","EPCL","GTYR","AKZO",
    "PAKT","PNSC","ASTL","ISL","MUGHAL","DAWH",
]

def http_post(url, payload, headers):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read())

def call_groq(prompt):
    for model in GROQ_MODELS:
        try:
            data = http_post(
                "https://api.groq.com/openai/v1/chat/completions",
                {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a PSX equity analyst. Respond with valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3, "max_tokens": 1000,
                },
                {"Content-Type": "application/json", "Authorization": "Bearer " + GROQ_KEY}
            )
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            e.read()
            if e.code in (429, 503): continue
        except Exception as e:
            print("Groq " + model + ": " + str(e))
            continue
    raise ValueError("All Groq models failed")

def call_gemini(prompt):
    for model in GEMINI_MODELS:
        try:
            data = http_post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                + model + ":generateContent?key=" + GEMINI_KEY,
                {"contents": [{"parts": [{"text": prompt}]}],
                 "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}},
                {"Content-Type": "application/json"}
            )
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        except urllib.error.HTTPError as e:
            e.read()
            if e.code in (429, 503, 404): continue
        except Exception as e:
            print("Gemini: " + str(e))
            continue
    raise ValueError("All Gemini models failed")

def call_ai(prompt):
    if GROQ_KEY:
        try: return call_groq(prompt)
        except Exception as e: print("Groq failed: " + str(e))
    if GEMINI_KEY:
        return call_gemini(prompt)
    raise ValueError("No AI key configured")

def parse_json(text):
    text = text.replace("```json","").replace("```","").strip()
    try: return json.loads(text)
    except: pass
    s = text.find("{")
    e = text.rfind("}") + 1
    if s >= 0 and e > s:
        return json.loads(text[s:e])
    raise ValueError("No JSON found")

def fallback_report(symbol, price, change_pct, rsi, pe, reason=""):
    stop_loss = round(price * 0.95, 2)
    target_1  = round(price * 1.08, 2)
    target_2  = round(price * 1.15, 2)
    msg = "AI rate limited. Wait 1 minute and retry." if "429" in str(reason) else "Retry for full AI analysis."
    return {
        "recommendation": "hold", "confidence": 45,
        "summary": symbol + " at Rs " + str(price) + ". " + msg,
        "technical_notes": "Price: Rs " + str(price) + " | Change: " + str(change_pct) + "% | RSI: " + str(rsi),
        "fundamental_notes": "P/E: " + str(pe),
        "news_impact": "Retry for Pakistan macro analysis.",
        "bull_case": msg, "bear_case": msg,
        "entry_price": price, "stop_loss": stop_loss,
        "target_1": target_1, "target_2": target_2, "risk_level": "medium",
    }

# ─── Routes ─────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status":"ok","groq":bool(GROQ_KEY),"gemini":bool(GEMINI_KEY)}

@app.get("/test-ai")
def test_ai():
    try:
        text = call_ai("Say hello in one word only.")
        return {"success": True, "response": text.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/symbols")
def symbols():
    return {"symbols": TOP_STOCKS, "count": len(TOP_STOCKS)}

@app.get("/market-watch")
def market_watch():
    """Fast — no OHLCV fetch per stock, just price+change"""
    result = []
    for sym in TOP_STOCKS:
        try:
            df = psxdata.quote(sym)
            if df is None or len(df) == 0:
                continue
            row = df.iloc[0].to_dict()
            price = safe_float(row.get("price"))
            if price <= 0:
                continue
            stock = quote_row_to_stock(sym, row, include_ohlcv=False)
            result.append(stock)
        except:
            continue
    if not result:
        raise HTTPException(status_code=500, detail="No data fetched")
    return result

@app.get("/quote/{symbol}")
def quote_endpoint(symbol: str):
    """Detailed quote WITH real OHLCV — used by stock detail screen"""
    try:
        df = psxdata.quote(symbol.upper())
        if df is None or len(df) == 0:
            raise HTTPException(status_code=404, detail="Not found")
        row   = df.iloc[0].to_dict()
        stock = quote_row_to_stock(symbol.upper(), row, include_ohlcv=True)
        return stock
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/history/{symbol}")
def history(symbol: str, days: int = 365):
    try:
        end   = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        df = psxdata.stocks(symbol.upper(), start=start, end=end)
        if hasattr(df, "reset_index"):
            records = df.reset_index().to_dict(orient="records")
            clean = [{str(k): (v.isoformat() if hasattr(v,"isoformat") else v)
                      for k,v in r.items()} for r in records]
            return sanitize(clean)
        return []
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/research")
def research(body: dict):
    symbol     = str(body.get("symbol", "UNKNOWN"))
    price      = safe_float(body.get("price", 0))
    change_pct = safe_float(body.get("changePct", 0))
    rsi        = str(body.get("rsi", "N/A"))
    pe         = str(body.get("pe", "N/A"))
    div_yield  = str(body.get("divYield", "N/A"))
    sector     = str(body.get("sector", "N/A"))
    stop_loss  = round(price * 0.95, 2)
    target_1   = round(price * 1.08, 2)
    target_2   = round(price * 1.15, 2)

    prompt = (
        "You are a senior PSX equity research analyst.\n"
        "Stock: " + symbol + " | Sector: " + sector + "\n"
        "Price: Rs " + str(price) + " | Change: " + str(change_pct) + "%\n"
        "RSI-14: " + rsi + " | P/E: " + pe + " | Div Yield: " + div_yield + "%\n"
        "Market: KSE-100, Pakistan, PKR. Date: July 2026.\n\n"
        "Output ONLY valid JSON. No text before or after:\n"
        '{"recommendation":"buy","confidence":70,'
        '"summary":"3-4 sentence executive summary with specific insights.",'
        '"technical_notes":"RSI interpretation, price action, support/resistance.",'
        '"fundamental_notes":"P/E valuation, dividend yield, sector position.",'
        '"news_impact":"Pakistan macro: interest rates, PKR, inflation, sector outlook.",'
        '"bull_case":"3 specific bullish catalysts for ' + symbol + '.",'
        '"bear_case":"3 specific risks and bearish scenarios.",'
        '"entry_price":' + str(price) + ","
        '"stop_loss":' + str(stop_loss) + ","
        '"target_1":' + str(target_1) + ","
        '"target_2":' + str(target_2) + ","
        '"holding_period":"3-6 months",'
        '"risk_level":"medium"}'
    )

    try:
        text   = call_ai(prompt)
        report = parse_json(text)
        report.setdefault("recommendation", "hold")
        report.setdefault("confidence", 50)
        report.setdefault("entry_price", price)
        report.setdefault("stop_loss", stop_loss)
        report.setdefault("target_1", target_1)
        report.setdefault("target_2", target_2)
        report.setdefault("risk_level", "medium")
        return sanitize(report)
    except Exception as e:
        print("Research error: " + str(e))
        return fallback_report(symbol, price, change_pct, rsi, pe, str(e))
