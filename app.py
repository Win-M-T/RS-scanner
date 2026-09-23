"""
Relative Strength Scanner
Plots every ticker on Week RS (x) vs Month RS (y), 0-100, ranked against each other
after subtracting the benchmark's return (default SPY).
"""
import pandas as pd
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

# ---------- Sidebar controls ----------
st.sidebar.title("Settings")
universe = st.sidebar.selectbox("What to scan", list(UNIVERSES))
if universe == "My own list":
    raw = st.sidebar.text_area("Tickers (spaces or commas)", "NVDA, AMD, SMCI, TSLA, PLTR, COIN")
    tickers = [t.strip().upper() for t in raw.replace(",", " ").split() if t.strip()]
else:
    tickers = UNIVERSES[universe]
benchmark = st.sidebar.text_input("Benchmark", "SPY").strip().upper()
short_days = st.sidebar.number_input("Short lookback (trading days) - X axis", 2, 60, 5)
long_days = st.sidebar.number_input("Long lookback (trading days) - Y axis", 5, 250, 21)
st.sidebar.caption("5 days = 1 week, 21 days = 1 month, 63 days = 3 months.")


# ---------- Data ----------
@st.cache_data(ttl=60 * 30, show_spinner="Downloading prices...")
def get_prices(symbols: tuple) -> pd.DataFrame:
    df = yf.download(list(symbols), period="1y", auto_adjust=True, progress=False)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(symbols[0])
    return df.dropna(how="all")


def compute_rs(prices: pd.DataFrame, bench: str, short: int, long: int) -> pd.DataFrame:
    """Return vs benchmark over each lookback, then percentile-rank 0-100."""
    ret_s = prices.iloc[-1] / prices.iloc[-1 - short] - 1
    ret_l = prices.iloc[-1] / prices.iloc[-1 - long] - 1
    out = pd.DataFrame({
        "Short vs bench %": (ret_s - ret_s[bench]) * 100,
        "Long vs bench %": (ret_l - ret_l[bench]) * 100,
    }).drop(index=bench).dropna()
    # rank 0 (worst) .. 100 (best)
    n = len(out)
    out["Week RS"] = (out["Short vs bench %"].rank() - 1) / max(n - 1, 1) * 100
    out["Month RS"] = (out["Long vs bench %"].rank() - 1) / max(n - 1, 1) * 100

    def quad(r):
        if r["Week RS"] >= 50 and r["Month RS"] >= 50: return "Strong"
        if r["Week RS"] < 50 and r["Month RS"] >= 50: return "Weakening"
        if r["Week RS"] >= 50: return "Improving"
        return "Weak"
    out["Quadrant"] = out.apply(quad, axis=1)
    out["Score"] = (out["Week RS"] + out["Month RS"]) / 2
    return out.sort_values("Score", ascending=False).round(1)


def make_chart(df: pd.DataFrame, names: dict) -> go.Figure:
    fig = go.Figure()
    shades = [(50, 100, 50, 100, "rgba(40,160,90,0.10)", "STRONG"),
              (0, 50, 50, 100, "rgba(200,150,40,0.08)", "WEAKENING"),
              (0, 50, 0, 50, "rgba(200,60,60,0.08)", "WEAK"),
              (50, 100, 0, 50, "rgba(60,110,220,0.10)", "IMPROVING")]
    for x0, x1, y0, y1, color, label in shades:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, fillcolor=color, line_width=0, layer="below")
        fig.add_annotation(x=(x0 + x1) / 2, y=y1 - 3, text=label, showarrow=False, font=dict(color="gray", size=11))
    fig.add_vline(x=50, line_dash="dash", line_color="gray")
    fig.add_hline(y=50, line_dash="dash", line_color="gray")
    labels = [names.get(t, t) for t in df.index]
    fig.add_trace(go.Scatter(
        x=df["Week RS"], y=df["Month RS"], mode="markers+text", text=labels,
        textposition="top center", marker=dict(size=11, color=df["Score"], colorscale="RdYlGn", cmin=0, cmax=100),
        customdata=df[["Short vs bench %", "Long vs bench %"]].values,
        hovertemplate="<b>%{text}</b><br>Week RS %{x:.0f} (%{customdata[0]:+.1f}% vs bench)"
                      "<br>Month RS %{y:.0f} (%{customdata[1]:+.1f}% vs bench)<extra></extra>",
    ))
    fig.update_layout(height=700, template="plotly_dark", showlegend=False,
                      xaxis=dict(title="Week RS", range=[-3, 103]),
                      yaxis=dict(title="Month RS", range=[-3, 103]),
                      margin=dict(l=40, r=20, t=30, b=40))
    return fig


# ---------- Page ----------
st.title("Relative Strength Scanner")
st.caption(f"Each dot = one ticker. Right = stronger than peers over {short_days} days, "
           f"up = stronger over {long_days} days (both after subtracting {benchmark}).")

if not tickers:
    st.info("Add some tickers in the sidebar.")
    st.stop()

symbols = tuple(sorted(set(tickers + [benchmark])))
prices = get_prices(symbols)
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

rs = compute_rs(prices, benchmark, int(short_days), int(long_days))
st.caption(f"Prices as of {prices.index[-1]:%b %d, %Y}")

names = SECTORS if universe.startswith("Sector") else {}
st.plotly_chart(make_chart(rs, names), width="stretch")

st.subheader("Leaders (Strong quadrant)")
st.dataframe(rs[rs["Quadrant"] == "Strong"], width="stretch")
with st.expander("All tickers"):
    st.dataframe(rs, width="stretch")
st.download_button("Download results (CSV)", rs.to_csv(), "rs_scan.csv", "text/csv")
