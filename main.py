from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psxdata
import json

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
        tickers = psxdata.tickers()
        result = []
        for _, row in tickers.iterrows():
            try:
                q = psxdata.quote(row["SYMBOL"])
                result.append({
                    "SYMBOL": str(row.get("SYMBOL", "")),
                    "COMPANY": str(row.get("COMPANY", "")),
                    "SECTOR": str(row.get("SECTOR", "")),
                    "LDCP": float(q.get("LDCP", 0) or 0),
                    "OPEN": float(q.get("OPEN", 0) or 0),
                    "HIGH": float(q.get("HIGH", 0) or 0),
                    "LOW": float(q.get("LOW", 0) or 0),
                    "CLOSE": float(q.get("CLOSE", 0) or 0),
                    "VOLUME": int(q.get("VOLUME", 0) or 0),
                    "CHANGE": float(q.get("CHANGE", 0) or 0),
                    "CHANGE%": float(q.get("CHANGE%", 0) or 0),
                })
            except Exception:
                pass
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/quote/{symbol}")
def quote(symbol: str):
    try:
        q = psxdata.quote(symbol.upper())
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
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
