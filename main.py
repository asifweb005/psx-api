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

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug-quote")
def debug_quote():
    """Shows exact structure of a single quote"""
    try:
        q = psxdata.quote("HBL")
        return {
            "type": str(type(q)),
            "value": str(q)[:1000],
            "keys": list(q.keys()) if isinstance(q, dict) else 
                    list(q.index) if hasattr(q, 'index') else "unknown"
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/debug")
def debug():
    try:
        data = psxdata.sectors()
        return {
            "type": str(type(data)),
            "columns": list(data.columns) if hasattr(data, 'columns') else [],
            "sample": str(data.head(2).to_dict()) if hasattr(data, 'head') else str(data)[:300]
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/market-watch")
def market_watch():
    try:
        # Get sector data for advances/declines
        sectors_df = psxdata.sectors()
        
        # Get all symbols
        symbols = psxdata.tickers()
        
        # Top PSX stocks to fetch quotes for
        top_stocks = [
            "HBL","UBL","MCB","ABL","BAFL","BAHL","MEBL",
            "OGDC","PPL","MARI","POL","PARCO",
            "ENGRO","EFERT","FATIMA","FFC","FFBL",
            "LUCK","DGKC","FCCL","KOHC","PIOC","CHCC",
            "HUBC","KAPCO","NCPL","KEL","PKGP",
            "PSO","APL","HASCOL",
            "TRG","SYS","TPLP","AVN","NETSOL",
            "SEARL","ABOT","HINOON","GLAXO","FEROZ",
            "PSMC","INDU","HCAR","GHNL","SAZEW",
            "NESTLE","UNITY","TREET","QUICE",
        ]
        
        result = []
        for sym in top_stocks:
            try:
                q = psxdata.quote(sym)
                if q is None:
                    continue
                
                # Convert Series to dict if needed
                if hasattr(q, 'to_dict'):
                    d = q.to_dict()
                elif isinstance(q, dict):
                    d = q
                else:
                    d = {}
                
                close = to_float(d.get("CLOSE") or d.get("close") or 
                                 d.get("Last") or d.get("last") or
                                 d.get("CURRENT") or d.get("current"))
                ldcp = to_float(d.get("LDCP") or d.get("ldcp") or
                                d.get("PREV_CLOSE") or d.get("prev_close"))
                change = to_float(d.get("CHANGE") or d.get("change"))
                change_pct = to_float(d.get("CHANGE%") or d.get("change%") or
                                      d.get("CHANGE_PCT") or d.get("change_pct"))
                
                if close == 0 and ldcp > 0:
                    close = ldcp
                
                result.append({
                    "SYMBOL": sym,
                    "COMPANY": str(d.get("COMPANY") or d.get("company") or 
                                  d.get("NAME") or d.get("name") or sym),
                    "SECTOR": str(d.get("SECTOR") or d.get("sector") or ""),
                    "LDCP": ldcp,
                    "OPEN": to_float(d.get("OPEN") or d.get("open")),
                    "HIGH": to_float(d.get("HIGH") or d.get("high")),
                    "LOW": to_float(d.get("LOW") or d.get("low")),
                    "CLOSE": close,
                    "VOLUME": to_int(d.get("VOLUME") or d.get("volume")),
                    "CHANGE": change,
                    "CHANGE%": change_pct,
                    "_raw_keys": list(d.keys())[:10],  # debug — remove later
                })
            except Exception as ex:
                result.append({"SYMBOL": sym, "error": str(ex)})
                continue
        
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/quote/{symbol}")
def quote(symbol: str):
    try:
        q = psxdata.quote(symbol.upper())
        if q is None:
            raise HTTPException(status_code=404, detail="Symbol not found")
        if hasattr(q, 'to_dict'):
            return q.to_dict()
        return q
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
        if hasattr(df, 'to_dict'):
            records = df.reset_index().to_dict(orient="records")
            clean = []
            for r in records:
                clean.append({
                    str(k): (v.isoformat() if hasattr(v, 'isoformat') else v)
                    for k, v in r.items()
                })
            return clean
        return df if isinstance(df, list) else []
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
