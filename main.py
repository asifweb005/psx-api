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

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/market-watch")
def market_watch():
    try:
        data = psxdata.tickers()
        
        # Handle both list and DataFrame
        if hasattr(data, 'iterrows'):
            # It's a DataFrame
            rows = []
            for _, row in data.iterrows():
                rows.append(dict(row))
            data = rows
        
        # data is now a list of dicts
        result = []
        for item in data:
            if isinstance(item, dict):
                symbol = str(item.get("SYMBOL") or item.get("symbol") or "")
            else:
                symbol = str(getattr(item, "SYMBOL", "") or "")
            
            if not symbol:
                continue
                
            result.append({
                "SYMBOL": symbol.upper(),
                "COMPANY": str(item.get("COMPANY") or item.get("company") or symbol),
                "SECTOR": str(item.get("SECTOR") or item.get("sector") or ""),
                "LDCP": float(item.get("LDCP") or item.get("ldcp") or 0),
                "OPEN": float(item.get("OPEN") or item.get("open") or 0),
                "HIGH": float(item.get("HIGH") or item.get("high") or 0),
                "LOW": float(item.get("LOW") or item.get("low") or 0),
                "CLOSE": float(item.get("CLOSE") or item.get("close") or 0),
                "VOLUME": int(item.get("VOLUME") or item.get("volume") or 0),
                "CHANGE": float(item.get("CHANGE") or item.get("change") or 0),
                "CHANGE%": float(item.get("CHANGE%") or item.get("change%") or 0),
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/quote/{symbol}")
def quote(symbol: str):
    try:
        q = psxdata.quote(symbol.upper())
        if hasattr(q, 'to_dict'):
            return q.to_dict()
        return q
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
            return df.to_dict(orient="records")
        if isinstance(df, list):
            return df
        return []
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/debug")
def debug():
    """Shows raw psxdata output so we can see the exact structure"""
    try:
        data = psxdata.tickers()
        sample = data[:2] if isinstance(data, list) else str(data)[:500]
        return {
            "type": str(type(data)),
            "sample": str(sample),
        }
    except Exception as e:
        return {"error": str(e)}
