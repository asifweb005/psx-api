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

def row_to_dict(row):
    """Convert DataFrame row or dict to plain dict"""
    if hasattr(row, 'to_dict'):
        return row.to_dict()
    if hasattr(row, '_asdict'):
        return row._asdict()
    return dict(row)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug")
def debug():
    try:
        # Check what sectors() returns — it has full market data
        data = psxdata.sectors()
        t = str(type(data))
        if hasattr(data, 'head'):
            sample = str(data.head(2).to_dict())
            cols = list(data.columns)
        elif isinstance(data, list):
            sample = str(data[:2])
            cols = list(data[0].keys()) if data else []
        else:
            sample = str(data)[:300]
            cols = []
        return {"type": t, "columns": cols, "sample": sample[:500]}
    except Exception as e:
        return {"error": str(e)}

@app.get("/market-watch")
def market_watch():
    try:
        # psxdata.sectors() returns DataFrame with sector-level data
        # We need per-stock data — use tickers() to get symbols
        # then batch quote them, or use the underlying market data
        
        symbols = psxdata.tickers()  # list of symbol strings
        
        # Get KSE100 constituents first (most important stocks)
        try:
            kse = psxdata.indices("KSE100")
            if hasattr(kse, 'tolist'):
                kse_symbols = kse.tolist()
            elif isinstance(kse, list):
                kse_symbols = kse
            else:
                kse_symbols = list(kse)
        except:
            kse_symbols = symbols[:50]

        result = []
        # Fetch quotes for top stocks (limit to avoid timeout)
        for sym in kse_symbols[:30]:
            try:
                q = psxdata.quote(sym)
                if q is None:
                    continue
                d = row_to_dict(q) if not isinstance(q, dict) else q
                
                result.append({
                    "SYMBOL": str(sym),
                    "COMPANY": str(d.get("COMPANY") or d.get("company") or sym),
                    "SECTOR": str(d.get("SECTOR") or d.get("sector") or ""),
                    "LDCP": to_float(d.get("LDCP") or d.get("ldcp")),
                    "OPEN": to_float(d.get("OPEN") or d.get("open")),
                    "HIGH": to_float(d.get("HIGH") or d.get("high")),
                    "LOW": to_float(d.get("LOW") or d.get("low")),
                    "CLOSE": to_float(d.get("CLOSE") or d.get("close")),
                    "VOLUME": to_int(d.get("VOLUME") or d.get("volume")),
                    "CHANGE": to_float(d.get("CHANGE") or d.get("change")),
                    "CHANGE%": to_float(d.get("CHANGE%") or d.get("change%") or d.get("CHANGE_PCT")),
                })
            except Exception as e:
                continue
        
        if not result:
            raise HTTPException(status_code=500, detail="No quotes fetched")
        
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/quote/{symbol}")
def quote(symbol: str):
    try:
        q = psxdata.quote(symbol.upper())
        if q is None:
            raise HTTPException(status_code=404, detail="Symbol not found")
        d = row_to_dict(q) if not isinstance(q, dict) else q
        return d
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
            records = df.to_dict(orient="records")
            # Convert any Timestamp keys to strings
            clean = []
            for r in records:
                clean.append({str(k): (v.isoformat() if hasattr(v,'isoformat') else v) 
                              for k,v in r.items()})
            return clean
        if isinstance(df, list):
            return df
        return []
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
