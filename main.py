from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psxdata
import os
import json
import urllib.request
import urllib.error

app = FastAPI(title="PSX Data & AI API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_KEY   = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]

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
    "803":"Sugar & Allied","816":"Textile Composite",
    "817":"Textile Spinning","818":"Textile Weaving",
    "825":"Vanaspati & Allied","826":"Paper & Board",
    "827":"Engineering","830":"Glass & Ceramics",
    "831":"Leatherware","833":"Transport",
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
        "MARKET_CAP": to_float(row.get("market_cap")),
        "LISTED_IN": str(row.get("listed_in") or ""),
    }

# All major PSX stocks — expanded list
TOP_STOCKS = [
    # Banks
    "HBL","UBL","MCB","ABL","BAFL","BAHL","MEBL","JSBL","SILK","NBP",
    "AKBL","BIFO","SNBL","BOP","FAYSAL","SCBPL","KASBB","SMBL","PIBTL",
    # Oil & Gas
    "OGDC","PPL","MARI","POL","PARCO","PSO","APL","SHEL","HASCOL","BYCO",
    "SNGP","SSGC","PKGS","TOTL",
    # Fertilizer
    "ENGRO","EFERT","FATIMA","FFC","FFBL","ACPL",
    # Cement
    "LUCK","DGKC","FCCL","KOHC","PIOC","CHCC","MLCF","GWLC","FLYNG",
    "BWCL","JVDC","SKMT","THCCL","POWER","ARPL",
    # Power
    "HUBC","KAPCO","KEL","NCPL","PKGP","JPGL","LPCL","NPKC","TSPL",
    "ATRL","IGAS","RLNG","SRVI",
    # Technology
    "TRG","SYS","NETSOL","AVN","TPLP","PSEL","HUMNL","MTMM",
    # Pharma
    "SEARL","ABOT","HINOON","GLAXO","FEROZ","SAPL","COLG","AGP",
    # Auto
    "PSMC","INDU","HCAR","SAZEW","GHNL","GHNI","MTL","ATLH",
    # Food
    "NESTLE","UNITY","TREET","QUICE","BHAT","FDISL","SFML",
    # Textile
    "GATM","NCL","CLOV","KTML","NML","RCML","THAL","ADMM",
    # Chemical
    "LOTCHEM","ICI","SITC","EPCL","GTYR","SIEM","AKZO",
    # Misc
    "PAKT","ISIL","PNSC","ASTL","ISL","MUGHAL","AICL","JLICL",
    "EFUG","DAWH","DWOOD","ENGROS","SHFA","PKOL","GGGL",
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
                    "temperature": 0.3,
                    "max_tokens": 1000,
                },
                {"Content-Type": "application/json", "Authorization": "Bearer " + GROQ_KEY}
            )
            text = data["choices"][0]["message"]["content"]
            print("Groq success: " + model)
            return text
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print("Groq " + model + ": " + str(e.code) + " " + body[:100])
            if e.code in (429, 503):
                continue
        except Exception as e:
            print("Groq exception: " + str(e))
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
            print("Gemini exception: " + str(e))
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
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
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
    """All available stock symbols"""
    return {"symbols": TOP_STOCKS, "count": len(TOP_STOCKS)}

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
def history(symbol: str, days: int = 365):
    try:
        from datetime import datetime, timedelta
        end = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        df = psxdata.stocks(symbol.upper(), start=start, end=end)
        if hasattr(df, "reset_index"):
            records = df.reset_index().to_dict(orient="records")
            return [{str(k): (v.isoformat() if hasattr(v,"isoformat") else v)
                     for k,v in r.items()} for r in records]
        return []
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/financials/{symbol}")
def financials(symbol: str):
    """Fetch financial statements from PSX for quarterly comparison"""
    try:
        import urllib.request
        url = "https://dps.psx.com.pk/financials/" + symbol.upper()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data
    except Exception as e:
        # Return empty structure — financials not always available
        return {
            "symbol": symbol.upper(),
            "quarterly": [],
            "annual": [],
            "error": str(e)
        }

@app.post("/research")
def research(body: dict):
    symbol     = str(body.get("symbol", "UNKNOWN"))
    price      = float(body.get("price", 0))
    change_pct = float(body.get("changePct", 0))
    rsi        = str(body.get("rsi", "N/A"))
    pe         = str(body.get("pe", "N/A"))
    div_yield  = str(body.get("divYield", "N/A"))
    sector     = str(body.get("sector", "N/A"))
    stop_loss  = round(price * 0.95, 2)
    target_1   = round(price * 1.08, 2)
    target_2   = round(price * 1.15, 2)

    prompt = (
        "You are a senior PSX (Pakistan Stock Exchange) equity research analyst.\n"
        "Write an institutional-style research report for:\n\n"
        "Stock: " + symbol + "\n"
        "Sector: " + sector + "\n"
        "Current Price: Rs " + str(price) + "\n"
        "Change Today: " + str(change_pct) + "%\n"
        "RSI-14: " + rsi + "\n"
        "P/E Ratio: " + pe + "\n"
        "Dividend Yield: " + div_yield + "%\n"
        "Market: KSE-100, Pakistan Stock Exchange, PKR currency\n\n"
        "Consider Pakistan's current economic context: interest rates, inflation, PKR stability, sector dynamics.\n"
        "Note: Today is July 2026. Base your analysis on general knowledge of this company and sector.\n\n"
        "Output ONLY a valid JSON object with these exact keys:\n"
        '{"recommendation":"strong_buy or buy or hold or sell or strong_sell",'
        '"confidence":75,'
        '"summary":"3-4 sentence executive summary with specific insights about ' + symbol + '.",'
        '"technical_notes":"Detailed technical analysis: price action, RSI interpretation, support/resistance levels.",'
        '"fundamental_notes":"Fundamental analysis: P/E valuation, dividend yield, sector position, balance sheet health.",'
        '"news_impact":"Pakistan macro factors: interest rate impact, PKR effect, sector-specific news and outlook for ' + sector + '.",'
        '"bull_case":"3 specific reasons to be bullish on ' + symbol + '.",'
        '"bear_case":"3 specific risks and reasons to be bearish on ' + symbol + '.",'
        '"entry_price":' + str(price) + ","
        '"stop_loss":' + str(stop_loss) + ","
        '"target_1":' + str(target_1) + ","
        '"target_2":' + str(target_2) + ","
        '"holding_period":"3-6 months",'
        '"risk_level":"low or medium or high"}'
    )

    try:
        text = call_ai(prompt)
        report = parse_json(text)
        report.setdefault("recommendation", "hold")
        report.setdefault("confidence", 50)
        report.setdefault("entry_price", price)
        report.setdefault("stop_loss", stop_loss)
        report.setdefault("target_1", target_1)
        report.setdefault("target_2", target_2)
        report.setdefault("risk_level", "medium")
        return report
    except Exception as e:
        print("Research error: " + str(e))
        return fallback_report(symbol, price, change_pct, rsi, pe, str(e))
