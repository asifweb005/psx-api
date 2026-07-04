# PSX Data API

Free PSX market data API powered by psxdata library.

## Deploy to Render (free)
1. Push this folder to a GitHub repo
2. Go to render.com → New Web Service → connect repo
3. It auto-detects Python and deploys

## Endpoints
- GET /health
- GET /market-watch  — all stocks with live quotes
- GET /quote/{symbol} — single stock quote
- GET /history/{symbol} — 1 year OHLCV history
