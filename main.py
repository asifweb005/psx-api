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

def quote_to_stock(sym, df):
    """Convert psxdata.quote() DataFrame row to our standard format"""
    if df is None or len(df) == 0:
        return None
    # Get first row as dict
    row = df.iloc[0].to_dict()
    
    # psxdata columns (from debug): symbol, sector, ..., free_float, volume_avg_30d
    # Get price fields — check all possible names
    close  = to_float(row.get("close") or row.get("CLOSE") or row.get("last_price") or 0)
    ldcp   = to_float(row.get("ldcp") or row.get("LDCP") or row.get("prev_close") or 0)
    open_  = to_float(row.get("open") or row.get("OPEN") or 0)
    high   = to_float(row.get("high") or row.get("HIGH") or 0)
    low    = to_float(row.get("low") or row.get("LOW") or 0)
    vol    = to_int(row.get("volume") or row.get("VOLUME") or 0)
    change = to_float(row.get("change") or row.get("CHANGE") or 0)
    chgpct = to_float(row.get("change_pct") or row.get("CHANGE%") or row.get("change%") or 0)
    sector = str(row.get("sector") or row.get("SECTOR") or "")
    name   = str(row.get("company") or row.get("COMPANY") or row.get("name") or sym)

    if close == 0: close = ldcp

    return {
        "SYMBOL": sym,
        "COMPANY": name,
        "SECTOR": sector,
        "LDCP": ldcp,
        "OPEN": open_,
        "HIGH": high,
        "LOW": low,
        "CLOSE": close,
        "VOLUME": vol,
        "CHANGE": change,
        "CHANGE%": chgpct,
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug-quote")
def debug_quote():
    """Shows ALL columns of a single quote"""
    try:
        df = psxdata.quote("HBL")
        row = df.iloc[0].to_dict()
        return {
            "columns": list(df.columns),
            "row": {k: str(v) for k, v in row.items()}
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/market-watch")
def market_watch():
    try:
        top_stocks = [
            "HBL","UBL","MCB","ABL","BAFL","BAHL","MEBL",
            "OGDC","PPL","MARI","POL",
            "ENGRO","EFERT","FATIMA","FFC",
            "LUCK","DGKC","FCCL","KOHC","PIOC",
            "HUBC","KAPCO","KEL",
            "PSO","APL",
            "TRG","SYS","NETSOL",
            "SEARL","ABOT","HINOON",
            "PSMC","INDU","HCAR",
            "NESTLE","UNITY",
        ]
        result = []
        for sym in top_stocks:
            try:
                df = psxdata.quote(sym)
                stock = quote_to_stock(sym, df)
                if stock:
                    result.append(stock)
            except:
                continue
        if not result:
            raise HTTPException(status_code=500, detail="No data fetched")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/quote/{symbol}")
def quote(symbol: str):
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
