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
    try:
        df = yf.download(list(symbols), period="1y", auto_adjust=True, progress=False)["Close"]
    except Exception:
        return pd.DataFrame()
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
# Stage colors follow the "Cycle of Price Action" chart
STAGES = {
    "1A": ("Upward Pivot", "#F0A36B"), "1B": ("Mean Reversion", "#F5E663"),
    "2A": ("Bullish Trend", "#A8E6A1"), "2B": ("Breakout Confirm", "#3CC47C"),
    "2C": ("Extended Bullish", "#FFFFFF"), "3A": ("Bullish Fade", "#8FD3F4"),
    "3B": ("Fade Confirmation", "#4A90D9"), "4A": ("Bearish Trend", "#F7A8A8"),
    "4B": ("Breakdown Confirm", "#E74C4C"), "4C": ("Extended Bearish", "#F07BF0"),
    "?": ("Unknown", "#777777"),
}
STAGE_ORDER = list(STAGES)
PALETTE = px.colors.qualitative.Plotly + px.colors.qualitative.Dark24

# (key, regex patterns, required?)
COLUMNS = [
    ("Symbol", [r"^symbol$", r"^ticker$", r"symbol", r"ticker"], True),
    ("Week %", [r"perf.*1\s*w", r"1\s*week", r"perf.*week"], True),
    ("Month %", [r"perf.*1\s*m(?!o)", r"perf.*1\s*month", r"1\s*month"], True),
    ("Day %", [r"^change\s*%$", r"^change\s*%\s*(1\s*d|1d|day)?$", r"^chg\s*%"], False),
    ("Quarter %", [r"perf.*3\s*m(?!o)", r"perf.*3\s*month", r"3\s*month"], False),
    ("6 Month %", [r"perf.*6\s*m(?!o)", r"perf.*6\s*month", r"6\s*month"], False),
    ("Year %", [r"perf.*1\s*y", r"1\s*year", r"perf.*52\s*w"], False),
    ("Sector", [r"^sector$", r"sector"], False),
    ("Industry", [r"^industry$", r"industry"], False),
    ("Market cap", [r"^market\s*cap(italization)?$", r"market\s*cap(?!.*currency)"], False),
    ("Price", [r"^price$", r"^close$", r"^last$", r"^price(?!.*currency)"], False),
    ("EMA 10", [r"exponential moving average\s*\(10\)", r"\bema\s*\(?10\b"], False),
    ("EMA 20", [r"exponential moving average\s*\(20\)", r"\bema\s*\(?20\b", r"exponential moving average\s*\(21\)", r"\bema\s*\(?21\b"], False),
    ("SMA 50", [r"simple moving average\s*\(50\)", r"\bsma\s*\(?50\b"], False),
    ("SMA 200", [r"simple moving average\s*\(200\)", r"\bsma\s*\(?200\b"], False),
    ("ATR", [r"average true range", r"\batr\b"], False),
]
TIMEFRAMES = [("DAY", "Day %"), ("WK", "Week %"), ("MTH", "Month %"), ("QTR", "Quarter %"),
              ("6M", "6 Month %"), ("1Y", "Year %")]


def guess_col(cols, patterns):
    for p in patterns:
        for c in cols:
            if re.search(p, str(c), re.IGNORECASE):
                return c
    return None


def to_number(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace("−", "-").str.replace(r"[%,\s$]", "", regex=True),
                         errors="coerce")


def pct_rank(s: pd.Series) -> pd.Series:
    n = s.notna().sum()
    return ((s.rank() - 1) / max(n - 1, 1) * 100).round(0)


def classify_stage(r) -> str:
    """Approximate stage (1A-4C) from price vs. 10/20 EMAs and 50/200 SMAs.
    A simplified take on the Cycle of Price Action, not Steve Jacobs' exact rules."""
    p, e10, e20, s50, s200 = r["Price"], r["EMA 10"], r["EMA 20"], r["SMA 50"], r["SMA 200"]
    if any(pd.isna(v) for v in (p, e10, e20, s50)):
        return "?"
    s200 = s50 if pd.isna(s200) else s200
    atr = r.get("ATR", float("nan"))
    ext = (p - s50) / atr if pd.notna(atr) and atr > 0 else (p / s50 - 1) * 100 / 3.5  # ~25% = 7 "ATRs"
    bull_short = p > e10 and e10 > e20
    bear_short = p < e10 and e10 < e20
    if bull_short:
        if ext >= 7:
            return "2C"
        if e20 > s50 > s200 and p > s50:
            return "2B"
        return "2A" if p > s50 else "1B"
    if bear_short:
        if ext <= -7:
            return "4C"
        if e20 < s50 < s200 and p < s50:
            return "4B"
        return "4A" if p < s50 else "3B"
    if p > e10:                      # price turning up through falling EMAs
        return "2A" if p > s50 else "1A"
    return "3A" if p > s50 else "4A"  # price slipping under rising EMAs


def rank_color(v) -> str:
    if pd.isna(v):
        return "transparent"
    if v >= 50:
        a = 0.15 + (v - 50) / 50 * 0.55
        return f"rgba(46,160,90,{a:.2f})"
    a = 0.15 + (50 - v) / 50 * 0.55
    return f"rgba(210,60,60,{a:.2f})"


def chg_html(v) -> str:
    if pd.isna(v):
        return ""
    c = "#4cd97b" if v >= 0 else "#ff6b6b"
    return f'<span style="color:{c};font-size:10px;margin-left:4px">{v:+.1f}%</span>'


CSS = """<style>
.rs-wrap{overflow-x:auto}
table.rs{border-collapse:collapse;font-size:12px;width:100%;color:#ddd}
table.rs th{color:#8a93a6;font-weight:600;text-align:center;padding:6px 4px;border-bottom:1px solid #333;font-size:11px}
table.rs td{padding:5px 4px;border-bottom:1px solid #262b36;text-align:center;vertical-align:middle}
table.rs td.name{text-align:left;white-space:nowrap;font-weight:600}
table.rs td.chips{text-align:left}
.chip{display:inline-block;background:#1b2130;border-left:3px solid #888;padding:2px 6px;margin:2px 3px 2px 0;border-radius:3px;font-weight:700;font-size:11px;white-space:nowrap}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
.card{background:#151a24;border-radius:6px;overflow:hidden;font-size:12px;color:#ddd}
.card .hd{display:flex;justify-content:space-between;padding:5px 8px;font-weight:700;color:#fff}
.card .sub{display:flex;justify-content:space-between;padding:3px 8px;color:#8a93a6;font-size:10px}
.row{display:flex;align-items:center;justify-content:space-between;padding:3px 8px;margin:2px 4px;background:#1b2130;border-left:3px solid #888;border-radius:3px}
.badge{display:inline-block;border:1px solid;border-radius:4px;padding:0 4px;font-size:10px;margin-left:4px;font-weight:700}
.circ{display:inline-block;border:1.5px solid;border-radius:50%;width:22px;height:22px;line-height:19px;text-align:center;font-size:10px;margin-left:4px;font-weight:700}
.stagecol{background:#151a24;border-radius:6px;padding:0 0 6px 0;min-width:0}
.stagecol .hd{padding:6px;text-align:center;color:#111;font-weight:700;border-radius:6px 6px 0 0}
</style>"""


def html(s: str):
    """Render raw HTML (no leading spaces so Markdown doesn't turn it into a code block)."""
    st.markdown(CSS + s, unsafe_allow_html=True)


def score_circle(v) -> str:
    c = "#3CC47C" if v >= 70 else "#F5C542" if v >= 50 else "#E74C4C"
    return f'<span class="circ" style="border-color:{c};color:{c}">{v:.0f}</span>'


def stage_badge(sg) -> str:
    c = STAGES.get(sg, STAGES["?"])[1]
    return f'<span class="badge" style="border-color:{c};color:{c}">{sg}</span>'


def load_tradingview():
    st.caption("Scan thousands of stocks using TradingView's own data, sectors and industries.")
    with st.expander("How to export from TradingView (do this once a day)", expanded=False):
        st.markdown(
            "1. Open **Screener → Stocks** in TradingView and load your saved screen "
            "(for example: USA, market cap above 1B, no REITs).\n"
            "2. Add these **columns** (column settings button on the right of the table):\n"
            "   - Needed: **Performance % 1 week**, **Performance % 1 month**, **Sector**, **Industry**\n"
            "   - For the table: **Change %**, **Performance % 3 months**, **6 months**, **1 year**, **Market capitalization**\n"
            "   - For stages: **Price**, **Exponential Moving Average (10)**, **Exponential Moving Average (20)**, "
            "**Simple Moving Average (50)**, **Simple Moving Average (200)**, and optionally **Average True Range (14)**\n"
            "3. Click the **export / download** button above the table to save a CSV file.\n"
            "4. Drag that file into the box below.\n\n"
            "Tip: save the screen with these columns once, so tomorrow it's just open → export → upload."
        )
    up = st.file_uploader("TradingView screener CSV", type=["csv"])
    if up is None:
        st.info("Upload a TradingView screener export to begin.")
        st.stop()

    raw = pd.read_csv(up)
    cols = list(raw.columns)
    guesses = {k: guess_col(cols, pats) for k, pats, _ in COLUMNS}
    required = [k for k, _, req in COLUMNS if req]
    with st.sidebar.expander("Column matching", expanded=any(guesses[k] is None for k in required)):
        chosen = {}
        for key, _, _ in COLUMNS:
            opts = ["(none)"] + cols
            chosen[key] = st.selectbox(key, opts, index=opts.index(guesses[key]) if guesses[key] in cols else 0)
    for key in required:
        if chosen[key] == "(none)":
            st.error(f"Couldn't find the **{key}** column. Pick it under *Column matching* in the sidebar, "
                     "or add it to your TradingView screener and export again.")
            st.stop()

    df = pd.DataFrame({"Ticker": raw[chosen["Symbol"]].astype(str).str.split(":").str[-1]})
    for key, _, _ in COLUMNS[1:]:
        if key in ("Sector", "Industry"):
            df[key] = raw[chosen[key]].fillna("Unknown").astype(str) if chosen[key] != "(none)" else "Unknown"
        else:
            df[key] = to_number(raw[chosen[key]]) if chosen[key] != "(none)" else float("nan")
    df = df.dropna(subset=["Week %", "Month %"]).drop_duplicates("Ticker").reset_index(drop=True)
    df["Market cap ($B)"] = (df["Market cap"] / 1e9).round(1)
    df["Stage"] = df.apply(classify_stage, axis=1)
    return df


def run_tradingview():
    df = load_tradingview()
    has_groups = (df["Industry"] != "Unknown").any()
    has_stage = (df["Stage"] != "?").any()

    # --- stock-level ranks for every timeframe ---
    stocks = add_rank(df, "Week %", "Month %")
    for tf, col in TIMEFRAMES:
        stocks[tf] = pct_rank(stocks[col])
    comp_cols = [tf for tf, col in TIMEFRAMES[1:] if stocks[col].notna().any()]
    stocks["COMP"] = stocks[comp_cols].mean(axis=1).round(0)

    sectors_sorted = sorted(df["Sector"].unique())
    sector_color = {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(sectors_sorted)}

    # --- sidebar ---
    st.sidebar.markdown("---")
    views = (["Leading groups - table", "Leading groups - cards", "Industries (quadrant)", "Sectors (quadrant)"]
             if has_groups else [])
    if has_stage:
        views.append("Stage analysis")
    views.append("Stocks (quadrant)")
    view = st.sidebar.radio("Show", views)
    min_stocks = st.sidebar.slider("Min stocks per group", 1, 20, 3) if has_groups else 1
    st.sidebar.caption("Group strength = median performance of its stocks, ranked 0-100 against other groups. "
                       "Score = average of Week RS and Month RS. COMP = average of all timeframes.")
    if has_stage:
        stage_pick = st.sidebar.multiselect("Stages to include", STAGE_ORDER[:-1], default=STAGE_ORDER[:-1])
    else:
        stage_pick = STAGE_ORDER

    def groups(by):
        agg = {"Stocks": ("Ticker", "size")}
        for tf, col in TIMEFRAMES:
            agg[col] = (col, "median")
        g = df.groupby(by).agg(**agg)
        if by == "Industry":
            g["Sector"] = df.groupby("Industry")["Sector"].agg(lambda s: s.mode().iat[0])
        g = g[g["Stocks"] >= min_stocks].reset_index()
        g = add_rank(g, "Week %", "Month %")
        for tf, col in TIMEFRAMES:
            g[tf] = pct_rank(g[col])
        g["COMP"] = g[comp_cols].mean(axis=1).round(0)
        return g

    st.caption(f"{len(df):,} stocks loaded from your TradingView export."
               + ("" if has_stage else "  Add the Price and moving-average columns to your export to see stages."))
    in_stage = stocks[stocks["Stage"].isin(stage_pick)]

    def stock_list(industry, limit, order):
        s = in_stage[in_stage["Industry"] == industry]
        if order == "Largest market cap first" and s["Market cap"].notna().any():
            s = s.sort_values("Market cap", ascending=False)
        else:
            s = s.sort_values("Score", ascending=False)
        return s.head(limit)

    result = stocks

    # ---------------- Leading groups: table ----------------
    if view == "Leading groups - table":
        ind = groups("Industry")
        c1, c2, c3 = st.columns(3)
        n_groups = c1.slider("Industries to show", 5, 60, 20)
        n_chips = c2.slider("Stocks per industry", 5, 40, 25)
        order = c3.selectbox("Stock order", ["Largest market cap first", "Strongest first"])
        sort_by = st.radio("Rank industries by", ["Score", "COMP"], horizontal=True)
        ind = ind.sort_values(sort_by, ascending=False).head(n_groups)
        tfs = [tf for tf, col in TIMEFRAMES if ind[col].notna().any()]
        head = "".join(f"<th>{t}</th>" for t in ["INDUSTRY", "# STK"] + tfs + ["COMP", "SCORE"])
        head += '<th style="text-align:left">STOCKS</th>'
        rows = []
        for _, r in ind.iterrows():
            cells = f'<td class="name" style="border-left:3px solid {sector_color[r["Sector"]]}">{r["Industry"]}</td>'
            cells += f'<td>{int(r["Stocks"])}</td>'
            for tf in tfs + ["COMP", "Score"]:
                cells += f'<td style="background:{rank_color(r[tf])}">{"" if pd.isna(r[tf]) else int(r[tf])}</td>'
            chips = "".join(
                f'<span class="chip" style="border-left-color:{STAGES[s["Stage"]][1]}" title="Stage {s["Stage"]} · Score {s["Score"]:.0f}">'
                f'{s["Ticker"]}{chg_html(s["Day %"])}</span>'
                for _, s in stock_list(r["Industry"], n_chips, order).iterrows()
            )
            cells += f'<td class="chips">{chips}</td>'
            rows.append(f"<tr>{cells}</tr>")
        html(f'<div class="rs-wrap"><table class="rs"><tr>{head}</tr>{"".join(rows)}</table></div>')
        st.caption("Chip stripe color = stock stage (see Stage analysis). Numbers are 0-100 ranks vs. other industries.")
        result = ind

    # ---------------- Leading groups: cards ----------------
    elif view == "Leading groups - cards":
        ind = groups("Industry")
        c1, c2, c3 = st.columns(3)
        n_groups = c1.slider("Industries to show", 4, 48, 12)
        n_rows = c2.slider("Stocks per card", 3, 30, 15)
        order = c3.selectbox("Stock order", ["Largest market cap first", "Strongest first"])
        ind = ind.sort_values("Score", ascending=False).head(n_groups)
        cards = []
        for _, r in ind.iterrows():
            sl = stock_list(r["Industry"], n_rows, order)
            body = "".join(
                f'<div class="row" style="border-left-color:{STAGES[s["Stage"]][1]}">'
                f'<span><b>{s["Ticker"]}</b>{chg_html(s["Day %"])}</span>'
                f'<span>{stage_badge(s["Stage"])}{score_circle(s["Score"])}</span></div>'
                for _, s in sl.iterrows()
            )
            cards.append(
                f'<div class="card"><div class="hd" style="background:{sector_color[r["Sector"]]}">'
                f'<span>{r["Industry"]}</span><span>{r["Score"]:.0f}</span></div>'
                f'<div class="sub"><span>Wk {r["Week RS"]:.0f} · Mth {r["Month RS"]:.0f}</span>'
                f'<span>{len(sl)}/{int(r["Stocks"])}</span></div>{body}</div>'
            )
        html(f'<div class="cards">{"".join(cards)}</div>')
        st.caption("Header color = sector. Badge = stage. Circle = the stock's own RS score (0-100).")
        result = ind

    # ---------------- Stage analysis ----------------
    elif view == "Stage analysis":
        scope = st.radio("Stocks", ["All stocks", "Only top-half industries"], horizontal=True)
        pool = stocks
        if scope == "Only top-half industries" and has_groups:
            ind = groups("Industry")
            pool = pool[pool["Industry"].isin(set(ind.loc[ind["Score"] >= 50, "Industry"]))]
        pool = pool[pool["Stage"] != "?"]
        counts = pool["Stage"].value_counts().reindex(STAGE_ORDER[:-1], fill_value=0)
        bull = counts[["1A", "1B", "2A", "2B", "2C"]].sum()
        m1, m2, m3 = st.columns(3)
        m1.metric("Stocks", f"{len(pool):,}")
        m2.metric("Bullish stages (1A-2C)", f"{bull / max(len(pool), 1):.0%}")
        m3.metric("Watchable (1A-2B)", f'{counts[["1A", "1B", "2A", "2B"]].sum():,}')
        fig = go.Figure(go.Bar(x=counts.index, y=counts.values, marker_color=[STAGES[s][1] for s in counts.index],
                               text=counts.values, textposition="outside", cliponaxis=False))
        fig.update_layout(height=260, template="plotly_dark", margin=dict(l=20, r=20, t=30, b=20),
                          yaxis=dict(visible=False))
        st.plotly_chart(fig, width="stretch")
        per_col = st.slider("Stocks listed per stage", 5, 100, 25)
        order = st.selectbox("Order within each stage", ["Strongest first", "Largest market cap first"])
        cols_html = []
        for sg in STAGE_ORDER[:-1]:
            s = pool[pool["Stage"] == sg]
            s = (s.sort_values("Market cap", ascending=False) if order.startswith("Largest")
                 else s.sort_values("Score", ascending=False)).head(per_col)
            name, colr = STAGES[sg]
            rows = "".join(
                f'<div class="row" style="border-left-color:{sector_color[x["Sector"]]}">'
                f'<span><b>{x["Ticker"]}</b>{chg_html(x["Day %"])}</span>{score_circle(x["Score"])}</div>'
                for _, x in s.iterrows()
            )
            cols_html.append(f'<div class="stagecol"><div class="hd" style="background:{colr}">'
                             f'{counts[sg]}<br><span style="font-size:10px">{name} · {sg}</span></div>{rows}</div>')
        html('<div class="rs-wrap"><div style="display:grid;grid-template-columns:repeat(10,minmax(120px,1fr));gap:6px;font-size:12px;color:#ddd">'
             + "".join(cols_html) + "</div></div>")
        st.caption("Stages are estimated from price vs. the 10/20-day EMAs and 50/200-day SMAs "
                   "(a simplified version of the Cycle of Price Action). Stripe color = sector.")
        result = pool

    # ---------------- Quadrant views ----------------
    elif view == "Industries (quadrant)":
        ind = groups("Industry")
        st.plotly_chart(make_chart(ind, "Industry", "Sector", ["Stocks", "Week %", "Month %"]), width="stretch")
        st.dataframe(ind, width="stretch", hide_index=True)
        result = ind

    elif view == "Sectors (quadrant)":
        sec = groups("Sector")
        st.plotly_chart(make_chart(sec, "Sector", "Sector", ["Stocks", "Week %", "Month %"]), width="stretch")
        st.dataframe(sec, width="stretch", hide_index=True)
        result = sec

    else:  # Stocks (quadrant)
        shown = in_stage
        if has_groups:
            ind = groups("Industry")
            only_top = st.sidebar.checkbox("Only stocks in top-half industries (\"one rule\")", value=True)
            only_strong = st.sidebar.checkbox("Only stocks in the Strong quadrant", value=False)
            if only_top:
                keep = set(ind.loc[ind["Score"] >= 50, "Industry"])
                shown = shown[shown["Industry"].isin(keep)].merge(
                    ind[["Industry", "Score"]].rename(columns={"Score": "Industry score"}), on="Industry", how="left")
            if only_strong:
                shown = shown[shown["Quadrant"] == "Strong"]
        st.caption(f"Showing {len(shown):,} stocks. Ranks are against all {len(stocks):,} stocks in your export.")
        hover = [c for c in ["Industry", "Stage", "Week %", "Month %", "Market cap ($B)"] if c in shown.columns]
        st.plotly_chart(make_chart(shown, "Ticker", "Sector" if has_groups else None, hover), width="stretch")
        st.dataframe(shown, width="stretch", hide_index=True)
        result = shown

    st.download_button("Download results (CSV)", result.to_csv(index=False), "rs_scan.csv", "text/csv")


if source == SOURCE_LIVE:
    run_live()
else:
    run_tradingview()
