from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psxdata

app = FastAPI(title="PSX Data API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def to_float(v):
    try: return float(v) if v is not None else 0.0
    except: return 0.0

def to_int(v):
    try: return int(str(v).replace(",","")) if v is not None else 0
    except: return 0

# Sector code to name mapping
SECTOR_NAMES = {
    "807": "Commercial Banks", "806": "Insurance",
    "101": "Oil & Gas Exploration", "102": "Oil & Gas Marketing",
    "201": "Cement", "301": "Fertilizer",
    "401": "Automobile Assembler", "402": "Automobile Parts",
    "501": "Technology & Communication", "601": "Pharmaceuticals",
    "701": "Food & Personal Care", "801": "Power Generation",
    "901": "Textile Composite",
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
    pe        = to_float(row.get("pe_ratio"))
    div_yield = to_float(row.get("dividend_yield"))
    vol_avg   = to_float(row.get("volume_avg_30d"))

    # Derive change amount from price and change_pct
    # price = ldcp * (1 + change_pct/100)  =>  ldcp = price / (1 + change_pct/100)
    if change_pct != 0:
        ldcp = price / (1 + change_pct / 100)
        change = price - ldcp
    else:
        ldcp = price
        change = 0.0

    return {
        "SYMBOL": sym,
        "COMPANY": sym,  # psxdata doesn't return company name in quote
        "SECTOR": sector_name(row.get("sector", "")),
        "LDCP": round(ldcp, 2),
        "OPEN": price,   # not available — use price as proxy
        "HIGH": price,
        "LOW": price,
        "CLOSE": price,
        "VOLUME": to_int(vol_avg),
        "CHANGE": round(change, 2),
        "CHANGE%": change_pct,
        "PE_RATIO": pe,
        "DIVIDEND_YIELD": div_yield,
        "LISTED_IN": str(row.get("listed_in", "")),
    }

TOP_STOCKS = [
    "HBL","UBL","MCB","ABL","BAFL","BAHL","MEBL","SILK","JSBL",
    "OGDC","PPL","MARI","POL","PARCO",
    "ENGRO","EFERT","FATIMA","FFC","FFBL",
    "LUCK","DGKC","FCCL","KOHC","PIOC","CHCC",
    "HUBC","KAPCO","KEL","NCPL",
    "PSO","APL","HASCOL","SHEL",
    "TRG","SYS","NETSOL","AVN","TPLP",
    "SEARL","ABOT","HINOON","GLAXO","FEROZ",
    "PSMC","INDU","HCAR","SAZEW",
    "NESTLE","UNITY","TREET",
    "PAKT","LOTCHEM","ICI","SITC",
]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug-quote")
def debug_quote():
    try:
        df = psxdata.quote("HBL")
        row = df.iloc[0].to_dict()
        return {"columns": list(df.columns), "row": {k: str(v) for k,v in row.items()}}
    except Exception as e:
        return {"error": str(e)}

@app.get("/market-watch")
def market_watch():
    try:
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
            raise HTTPException(status_code=500, detail="No data")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
