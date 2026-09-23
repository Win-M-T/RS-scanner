"""
Relative Strength Scanner
Plots tickers (or whole industries/sectors) on Week RS (x) vs Month RS (y), ranked 0-100.
Two data sources:
  1. Live prices from Yahoo Finance (sector ETFs, large caps, or your own list)
  2. A CSV exported from the TradingView stock screener (scan thousands of stocks,
     grouped by TradingView's own sectors and industries)
"""
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="RS Scanner", layout="wide")

# ---------- Ticker lists ----------
SECTORS = {
    "XLE": "Energy", "XLK": "Technology", "XLF": "Financial", "XLV": "Healthcare",
    "XLY": "Consumer Cyclical", "XLP": "Consumer Defensive", "XLI": "Industrials",
    "XLB": "Basic Materials", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLC": "Communication Services",
}
LARGE_CAPS = """AAPL MSFT NVDA AMZN GOOGL META AVGO TSLA BRK-B JPM LLY V UNH XOM MA
JNJ PG HD COST ABBV WMT NFLX CRM BAC ORCL CVX KO MRK AMD PEP ADBE TMO LIN ACN MCD
CSCO WFC ABT GE DHR IBM QCOM CAT TXN INTU AMGN VZ PM ISRG NOW GS SPGI UBER CMCSA
NEE RTX PFE HON AMAT UNP LOW T BKNG ELV AXP SYK PGR BLK COP MS TJX VRTX LMT ETN
C BSX MDT SCHW ADP PLD REGN MU PANW CB DE MMC LRCX KLAC ANET SBUX BMY GILD ADI FI
SO MO DUK SHW CME CRWD PLTR APP""".split()
UNIVERSES = {
    "Sector ETFs (SPDR)": list(SECTORS),
    "Large-cap stocks (~100)": LARGE_CAPS,
    "My own list": [],
}
SOURCE_LIVE = "Live prices (Yahoo)"
SOURCE_TV = "TradingView screener export (CSV)"


# ---------- Shared helpers ----------
def add_rank(df: pd.DataFrame, short_col: str, long_col: str) -> pd.DataFrame:
    """Percentile-rank two performance columns into Week RS / Month RS (0 = worst, 100 = best)."""
    df = df.dropna(subset=[short_col, long_col]).copy()
    n = len(df)
    df["Week RS"] = (df[short_col].rank() - 1) / max(n - 1, 1) * 100
    df["Month RS"] = (df[long_col].rank() - 1) / max(n - 1, 1) * 100
    strong_w, strong_m = df["Week RS"] >= 50, df["Month RS"] >= 50
    df["Quadrant"] = "Weak"
    df.loc[strong_w & strong_m, "Quadrant"] = "Strong"
    df.loc[~strong_w & strong_m, "Quadrant"] = "Weakening"
    df.loc[strong_w & ~strong_m, "Quadrant"] = "Improving"
    df["Score"] = (df["Week RS"] + df["Month RS"]) / 2
    return df.sort_values("Score", ascending=False).round(1)


def make_chart(df: pd.DataFrame, label_col: str, color_col: str | None, hover_cols: list) -> go.Figure:
    show_text = len(df) <= 80
    fig = px.scatter(
        df, x="Week RS", y="Month RS",
        color=color_col if color_col else "Score",
        color_continuous_scale="RdYlGn" if not color_col else None,
        range_color=(0, 100) if not color_col else None,
        text=label_col if show_text else None,
        hover_name=label_col, hover_data={c: True for c in hover_cols},
    )
    fig.update_traces(marker=dict(size=10 if show_text else 7), textposition="top center", textfont_size=10)
    shades = [(50, 100, 50, 100, "rgba(40,160,90,0.10)", "STRONG"),
              (0, 50, 50, 100, "rgba(200,150,40,0.08)", "WEAKENING"),
              (0, 50, 0, 50, "rgba(200,60,60,0.08)", "WEAK"),
              (50, 100, 0, 50, "rgba(60,110,220,0.10)", "IMPROVING")]
    for x0, x1, y0, y1, color, label in shades:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, fillcolor=color, line_width=0, layer="below")
        fig.add_annotation(x=(x0 + x1) / 2, y=y1 - 3, text=label, showarrow=False, font=dict(color="gray", size=11))
    fig.add_vline(x=50, line_dash="dash", line_color="gray")
    fig.add_hline(y=50, line_dash="dash", line_color="gray")
    fig.update_layout(height=750, template="plotly_dark",
                      xaxis=dict(title="Week RS", range=[-3, 103]),
                      yaxis=dict(title="Month RS", range=[-3, 103]),
                      legend=dict(orientation="h", y=-0.12, title=None),
                      coloraxis_showscale=False,
                      margin=dict(l=40, r=20, t=30, b=40))
    return fig


# ---------- Sidebar ----------
st.sidebar.title("Settings")
source = st.sidebar.radio("Data source", [SOURCE_LIVE, SOURCE_TV])
st.title("Relative Strength Scanner")


# =====================================================================
# 1) LIVE PRICES (Yahoo)
# =====================================================================
@st.cache_data(ttl=60 * 30, show_spinner="Downloading prices...")
def get_prices(symbols: tuple) -> pd.DataFrame:
    df = yf.download(list(symbols), period="1y", auto_adjust=True, progress=False)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(symbols[0])
    return df.dropna(how="all")


def run_live():
    universe = st.sidebar.selectbox("What to scan", list(UNIVERSES))
    if universe == "My own list":
        raw = st.sidebar.text_area("Tickers (spaces or commas)", "NVDA, AMD, SMCI, TSLA, PLTR, COIN")
        tickers = [t.strip().upper() for t in raw.replace(",", " ").split() if t.strip()]
    else:
        tickers = UNIVERSES[universe]
    benchmark = st.sidebar.text_input("Benchmark", "SPY").strip().upper()
    short_days = int(st.sidebar.number_input("Short lookback (trading days) - X axis", 2, 60, 5))
    long_days = int(st.sidebar.number_input("Long lookback (trading days) - Y axis", 5, 250, 21))
    st.sidebar.caption("5 days = 1 week, 21 days = 1 month, 63 days = 3 months.")

    st.caption(f"Each dot = one ticker. Right = stronger than peers over {short_days} days, "
               f"up = stronger over {long_days} days (both after subtracting {benchmark}).")
    if not tickers:
        st.info("Add some tickers in the sidebar.")
        st.stop()

    prices = get_prices(tuple(sorted(set(tickers + [benchmark]))))
    if benchmark not in prices.columns or prices[benchmark].dropna().empty:
        st.error(f"Couldn't load the benchmark {benchmark}. Check the ticker and try again.")
        st.stop()
    prices = prices.dropna(axis=1, thresh=long_days + 2).ffill()
    missing = set(tickers) - set(prices.columns)
    if missing:
        st.warning("No data for: " + ", ".join(sorted(missing)))
    if len(prices) <= long_days + 1:
        st.error("Not enough price history for that lookback.")
        st.stop()

    ret_s = prices.iloc[-1] / prices.iloc[-1 - short_days] - 1
    ret_l = prices.iloc[-1] / prices.iloc[-1 - long_days] - 1
    df = pd.DataFrame({
        "Short vs bench %": (ret_s - ret_s[benchmark]) * 100,
        "Long vs bench %": (ret_l - ret_l[benchmark]) * 100,
    }).drop(index=benchmark)
    df.index.name = "Ticker"
    df = add_rank(df, "Short vs bench %", "Long vs bench %").reset_index()
    df["Name"] = df["Ticker"].map(SECTORS).fillna(df["Ticker"]) if universe.startswith("Sector") else df["Ticker"]

    st.caption(f"Prices as of {prices.index[-1]:%b %d, %Y}")
    st.plotly_chart(make_chart(df, "Name", None, ["Short vs bench %", "Long vs bench %"]), width="stretch")
    st.subheader("Leaders (Strong quadrant)")
    st.dataframe(df[df["Quadrant"] == "Strong"], width="stretch", hide_index=True)
    with st.expander("All tickers"):
        st.dataframe(df, width="stretch", hide_index=True)
    st.download_button("Download results (CSV)", df.to_csv(index=False), "rs_scan.csv", "text/csv")


# =====================================================================
# 2) TRADINGVIEW SCREENER EXPORT (CSV)
# =====================================================================
def guess_col(cols, patterns):
    """Return the first column whose name matches any regex pattern (case-insensitive)."""
    for p in patterns:
        for c in cols:
            if re.search(p, str(c), re.IGNORECASE):
                return c
    return None


def to_number(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[%,\s]", "", regex=True)
                         .str.replace("−", "-"), errors="coerce")


def run_tradingview():
    st.caption("Scan thousands of stocks using TradingView's own data, sectors and industries.")
    with st.expander("How to export from TradingView (do this once a day)", expanded=False):
        st.markdown(
            "1. Open **Screener → Stocks** in TradingView and load your saved screen "
            "(for example: USA, market cap above 1B, no REITs).\n"
            "2. Make sure these **columns** are showing (click the column settings to add them): "
            "**Performance % 1 week**, **Performance % 1 month**, **Sector**, **Industry**. "
            "Market cap is optional.\n"
            "3. Click the **export / download** button above the table to save a CSV file.\n"
            "4. Drag that file into the box below."
        )
    up = st.file_uploader("TradingView screener CSV", type=["csv"])
    if up is None:
        st.info("Upload a TradingView screener export to begin.")
        st.stop()

    raw = pd.read_csv(up)
    cols = list(raw.columns)
    guesses = {
        "Symbol": guess_col(cols, [r"^symbol$", r"^ticker$", r"symbol", r"ticker"]),
        "Week performance %": guess_col(cols, [r"perf.*1\s*w", r"1\s*week", r"perf.*week", r"\bweek"]),
        "Month performance %": guess_col(cols, [r"perf.*1\s*m(?!o)", r"perf.*1\s*month", r"1\s*month", r"perf.*month", r"\bmonth"]),
        "Sector": guess_col(cols, [r"^sector$", r"sector"]),
        "Industry": guess_col(cols, [r"^industry$", r"industry"]),
        "Market cap": guess_col(cols, [r"market\s*cap"]),
    }
    optional = {"Sector", "Industry", "Market cap"}
    with st.sidebar.expander("Column matching", expanded=any(guesses[k] is None for k in guesses if k not in optional)):
        chosen = {}
        for key, guess in guesses.items():
            opts = ["(none)"] + cols
            chosen[key] = st.selectbox(key, opts, index=opts.index(guess) if guess in cols else 0)
    for key in ["Symbol", "Week performance %", "Month performance %"]:
        if chosen[key] == "(none)":
            st.error(f"Couldn't find the **{key}** column. Pick it under *Column matching* in the sidebar, "
                     "or add it to your TradingView screener and export again.")
            st.stop()

    df = pd.DataFrame({
        "Ticker": raw[chosen["Symbol"]].astype(str).str.split(":").str[-1],
        "Week %": to_number(raw[chosen["Week performance %"]]),
        "Month %": to_number(raw[chosen["Month performance %"]]),
    })
    df["Sector"] = raw[chosen["Sector"]].fillna("Unknown") if chosen["Sector"] != "(none)" else "Unknown"
    df["Industry"] = raw[chosen["Industry"]].fillna("Unknown") if chosen["Industry"] != "(none)" else "Unknown"
    if chosen["Market cap"] != "(none)":
        df["Market cap ($B)"] = (to_number(raw[chosen["Market cap"]]) / 1e9).round(1)
    df = df.dropna(subset=["Week %", "Month %"]).drop_duplicates("Ticker")
    has_groups = (df["Industry"] != "Unknown").any()

    st.sidebar.markdown("---")
    views = ["Industries", "Sectors", "Stocks"] if has_groups else ["Stocks"]
    view = st.sidebar.radio("Show", views)
    min_stocks = st.sidebar.slider("Min stocks per group", 1, 20, 3) if has_groups else 1
    st.sidebar.caption("Group strength = median performance of the stocks in that group, then ranked 0-100.")

    stocks = add_rank(df, "Week %", "Month %")

    def groups(by):
        g = (df.groupby(by).agg(Stocks=("Ticker", "size"), **{"Week %": ("Week %", "median"),
                                                                "Month %": ("Month %", "median")}))
        if by == "Industry":
            g["Sector"] = df.groupby("Industry")["Sector"].agg(lambda s: s.mode().iat[0])
        g = g[g["Stocks"] >= min_stocks].reset_index()
        return add_rank(g, "Week %", "Month %")

    st.caption(f"{len(df):,} stocks loaded from your TradingView export.")

    if view == "Industries":
        ind = groups("Industry")
        st.plotly_chart(make_chart(ind, "Industry", "Sector", ["Stocks", "Week %", "Month %"]), width="stretch")
        st.subheader("Leading stocks in leading industries")
        st.caption("Industries in the Strong quadrant, with their strongest stocks (by stock Score).")
        lead = ind[ind["Quadrant"] == "Strong"].copy()
        top = (stocks.sort_values("Score", ascending=False).groupby("Industry")
               .apply(lambda s: ", ".join(f"{t} ({sc:.0f})" for t, sc in zip(s["Ticker"].head(8), s["Score"].head(8))),
                      include_groups=False))
        lead["Top stocks (score)"] = lead["Industry"].map(top)
        st.dataframe(lead, width="stretch", hide_index=True)
        with st.expander("All industries"):
            st.dataframe(ind, width="stretch", hide_index=True)
        result = ind

    elif view == "Sectors":
        sec = groups("Sector")
        st.plotly_chart(make_chart(sec, "Sector", "Sector", ["Stocks", "Week %", "Month %"]), width="stretch")
        st.dataframe(sec, width="stretch", hide_index=True)
        result = sec

    else:  # Stocks
        shown = stocks
        if has_groups:
            ind = groups("Industry")
            only_top = st.sidebar.checkbox("Only stocks in top-half industries (\"one rule\")", value=True)
            only_strong = st.sidebar.checkbox("Only stocks in the Strong quadrant", value=False)
            if only_top:
                keep = set(ind.loc[ind["Score"] >= 50, "Industry"])
                shown = shown[shown["Industry"].isin(keep)]
                shown = shown.merge(ind[["Industry", "Score"]].rename(columns={"Score": "Industry score"}),
                                    on="Industry", how="left")
            if only_strong:
                shown = shown[shown["Quadrant"] == "Strong"]
        st.caption(f"Showing {len(shown):,} stocks. Ranks are against all {len(stocks):,} stocks in your export.")
        hover = [c for c in ["Industry", "Week %", "Month %", "Market cap ($B)"] if c in shown.columns]
        st.plotly_chart(make_chart(shown, "Ticker", "Sector" if has_groups else None, hover), width="stretch")
        st.dataframe(shown, width="stretch", hide_index=True)
        result = shown

    st.download_button("Download results (CSV)", result.to_csv(index=False), "rs_scan.csv", "text/csv")


if source == SOURCE_LIVE:
    run_live()
else:
    run_tradingview()
