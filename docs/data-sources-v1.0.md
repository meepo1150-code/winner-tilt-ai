# Winner Tilt AI — Data Sources v1.0

**Prepared:** 2026-07-23

This document defines source priority. It does not imply that every source is free or already integrated.

## 1. Security master and listing status
Primary: Nasdaq Trader Symbol Directory and official NYSE listing directory.
Use this layer to validate symbol, exchange, issue type, and abnormal listing status.

## 2. Regulatory and company fundamentals
Primary: SEC EDGAR filings and company Investor Relations materials.
Use 10-K, 10-Q, 8-K, earnings releases, investor presentations, and conference-call materials.

## 3. Prices and volume
Prototype: a reputable market-data provider with adjusted daily OHLCV.
Production: licensed point-in-time data with corporate actions and delisted securities.

## 4. Analyst estimates and revisions
Use a licensed point-in-time estimates provider for production backtests.
Do not reconstruct historical estimate revisions from current snapshots.

## 5. Insider transactions
Primary: SEC Forms 3, 4, and 5.
Separate routine compensation activity from discretionary open-market purchases and sales.

## 6. News and catalysts
Priority: company filings and IR, regulators, then reputable financial news.
Store publication timestamp, event timestamp, source, affected entities, and confidence.

## 7. Backtest integrity
Production backtests require historical constituents, delisted securities, point-in-time fundamentals and estimates, corporate actions, and look-ahead controls.

## Official references
- Nasdaq Trader Symbol Directory: https://www.nasdaqtrader.com/trader.aspx?id=symbollookup
- Nasdaq Symbol Directory definitions: https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs
- SEC EDGAR: https://www.sec.gov/edgar/search/
- NYSE listings directory: https://www.nyse.com/listings_directory/stock
