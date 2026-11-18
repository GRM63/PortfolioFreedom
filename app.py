"""
Portfolio Monitor - Streamlit App
Live portfolio tracking via Freedom24/Tradernet API with yfinance charts.
Includes trade history management and Excel import/export.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import (
    PORTFOLIO_FILE,
    CHART_PERIODS,
    TRADERNET_LOGIN,
    TRADERNET_PASSWORD,
    DATA_SOURCE,
    DEFAULT_REFRESH_INTERVAL,
    REFRESH_INTERVALS,
)
from portfolio import load_portfolio, get_yfinance_ticker
from market_data import get_price_history
from trades import load_trades, save_trades, add_trade, get_trades_summary, TRADES_FILE
from file_manager import (
    import_portfolio_excel,
    import_trades_excel,
    export_portfolio_excel,
    export_trades_excel,
    get_file_info,
)
from alerts import (
    init_alerts,
    add_alert,
    remove_alert,
    get_alerts,
    AlertType,
    format_alert_type,
)

# Page config
st.set_page_config(
    page_title="Portfolio Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Oldest Streamlit with every API this app uses: st.dataframe(width="stretch")
# needs 1.48, st.plotly_chart(width="stretch") 1.51, and download_button with
# a callable `data` 1.52. Fail early with a clear message instead of a
# TypeError deep inside a fragment.
MIN_STREAMLIT = (1, 52)
_installed = tuple(int(part) for part in st.__version__.split(".")[:2])
if _installed < MIN_STREAMLIT:
    st.error(
        f"This app needs Streamlit {'.'.join(map(str, MIN_STREAMLIT))} or newer, "
        f"but {st.__version__} is installed. Run:\n\n"
        "`pip install -r requirements.txt`"
    )
    st.stop()

# Initialize session state
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if "refresh_interval" not in st.session_state:
    st.session_state.refresh_interval = DEFAULT_REFRESH_INTERVAL
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True
if "data_source" not in st.session_state:
    st.session_state.data_source = DATA_SOURCE

init_alerts()

API_AVAILABLE = bool(TRADERNET_LOGIN and TRADERNET_PASSWORD)
API_RETRY_SECONDS = 60  # after an API failure, use Excel for this long before retrying


def flash(message: str):
    """Queue a toast to show after the next st.rerun().

    Replaces the old `st.success(...); time.sleep(1); st.rerun()` pattern,
    which blocked the server for a second just so the message was readable.
    """
    st.session_state.flash = message


def show_flash():
    message = st.session_state.pop("flash", None)
    if message:
        st.toast(message, icon="✅")


def format_currency(value: float, currency: str = "EUR") -> str:
    """Format value as currency."""
    if value is None or pd.isna(value):
        return "N/A"
    symbol = "€" if currency == "EUR" else "$"
    return f"{symbol}{value:,.2f}"


def format_change(value: float, is_percent: bool = False) -> str:
    """Format change value with sign."""
    if value is None or pd.isna(value):
        return "N/A"
    sign = "+" if value > 0 else ""
    if is_percent:
        return f"{sign}{value:.2f}%"
    return f"{sign}{value:,.2f}"


def file_mtime(path: str) -> Optional[float]:
    """Last-modified time of a file, or None if it doesn't exist."""
    try:
        return Path(path).stat().st_mtime
    except FileNotFoundError:
        return None


# The Excel readers are cached on (path, mtime): the mtime argument isn't used
# inside the function, but it is part of the cache key, so the cache is
# invalidated automatically whenever the file changes on disk.
@st.cache_data(show_spinner=False)
def _load_trades_cached(path: str, mtime: Optional[float]) -> pd.DataFrame:
    return load_trades(path)


@st.cache_data(show_spinner=False)
def _load_portfolio_cached(path: str, mtime: Optional[float]) -> pd.DataFrame:
    return load_portfolio(path)


def get_trades() -> pd.DataFrame:
    """Trades from TRADES_FILE, re-read only when the file changes."""
    return _load_trades_cached(TRADES_FILE, file_mtime(TRADES_FILE))


def get_excel_portfolio() -> pd.DataFrame:
    """Portfolio from PORTFOLIO_FILE, re-read only when the file changes."""
    return _load_portfolio_cached(PORTFOLIO_FILE, file_mtime(PORTFOLIO_FILE))


@st.cache_resource
def get_api_client():
    """
    One Tradernet client per server process.

    cache_resource (unlike cache_data) returns the *same* object every time
    instead of a copy, which is what we want for a connection/session.
    """
    from tradernet import TradernetClient
    return TradernetClient(TRADERNET_LOGIN, TRADERNET_PASSWORD)


@st.cache_data(ttl=30)
def fetch_portfolio_from_api() -> pd.DataFrame:
    """Fetch portfolio data from Tradernet API."""
    if not API_AVAILABLE:
        raise ValueError("API credentials not configured")

    portfolio_data = get_api_client().get_portfolio_sync()

    if portfolio_data is None:
        raise ValueError("Failed to fetch portfolio from API")

    rows = []
    for pos in portfolio_data.positions:
        entry_value = pos.avg_price * pos.quantity
        rows.append({
            "ticker": pos.ticker,
            "yf_ticker": get_yfinance_ticker(pos.ticker),
            "quantity": pos.quantity,
            "entry_price": pos.avg_price,
            "entry_value": entry_value,
            "platform_price": pos.current_price,
            "platform_value": pos.current_value,
            "platform_profit": pos.profit,
            "platform_growth": pos.profit_pct,
        })

    return pd.DataFrame(rows)


def load_portfolio_data() -> tuple[pd.DataFrame, str, Optional[str]]:
    """
    Load portfolio data from the configured source.

    Returns (portfolio, source label, warning or None). Doesn't draw anything,
    so it can be called from both the main script and the live fragment.
    """
    warning = None

    if st.session_state.data_source == "api" and API_AVAILABLE:
        failed_at = st.session_state.get("api_failed_at")
        seconds_since_failure = (datetime.now() - failed_at).total_seconds() if failed_at else None

        if seconds_since_failure is None or seconds_since_failure >= API_RETRY_SECONDS:
            try:
                df = fetch_portfolio_from_api()
                st.session_state.api_failed_at = None
                return df, "Live data from Freedom24 API", None
            except Exception as e:
                # Remember the failure so the next reruns don't each wait
                # on a dead API before falling back.
                st.session_state.api_failed_at = datetime.now()
                st.session_state.api_error = str(e)
                seconds_since_failure = 0

        retry_in = int(API_RETRY_SECONDS - seconds_since_failure)
        warning = (f"API error: {st.session_state.get('api_error')}. "
                   f"Showing Excel data; retrying in {retry_in}s.")

    return get_excel_portfolio(), f"Data from {PORTFOLIO_FILE}", warning


def create_price_chart(ticker: str, period: str = "1mo") -> go.Figure:
    """Create a detailed price chart for a ticker."""
    hist = get_price_history(ticker, period)

    if hist is None or hist.empty:
        return None

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=hist.index,
        open=hist["Open"],
        high=hist["High"],
        low=hist["Low"],
        close=hist["Close"],
        name=ticker,
    ))

    # Vectorised: compares whole columns at once instead of looping per row
    colors = np.where(hist["Close"] < hist["Open"], "red", "green")

    fig.add_trace(go.Bar(
        x=hist.index,
        y=hist["Volume"],
        name="Volume",
        marker_color=colors,
        opacity=0.3,
        yaxis="y2",
    ))

    fig.update_layout(
        title=f"{ticker} Price History",
        yaxis_title="Price",
        xaxis_title="Date",
        yaxis2=dict(title="Volume", overlaying="y", side="right", showgrid=False),
        xaxis_rangeslider_visible=False,
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return fig


def render_sidebar(portfolio: pd.DataFrame):
    """Render the sidebar with settings."""
    st.sidebar.title("Settings")

    # Data source selection
    st.sidebar.subheader("Data Source")
    if API_AVAILABLE:
        source_options = ["api", "excel"]
        source_labels = ["Live API", "Excel File"]
        current_idx = source_options.index(st.session_state.data_source) if st.session_state.data_source in source_options else 0

        selected_source = st.sidebar.radio(
            "Source",
            options=source_options,
            format_func=lambda x: source_labels[source_options.index(x)],
            index=current_idx,
        )

        if selected_source != st.session_state.data_source:
            st.session_state.data_source = selected_source
            st.rerun()
    else:
        st.sidebar.caption("API: Not configured")
        st.sidebar.caption("Add credentials to .env file")

    # Auto-refresh settings
    if st.session_state.data_source == "api" and API_AVAILABLE:
        st.sidebar.divider()
        st.sidebar.subheader("Auto-Refresh")

        st.session_state.auto_refresh = st.sidebar.checkbox(
            "Enable auto-refresh",
            value=st.session_state.auto_refresh
        )

        refresh_options = dict(REFRESH_INTERVALS)
        labels = list(refresh_options)
        current = next((l for l, sec in refresh_options.items()
                        if sec == st.session_state.refresh_interval), labels[1])
        selected_interval = st.sidebar.selectbox(
            "Refresh interval",
            options=labels,
            index=labels.index(current),
            disabled=not st.session_state.auto_refresh
        )
        st.session_state.refresh_interval = refresh_options[selected_interval]

    if st.sidebar.button("Refresh Now"):
        fetch_portfolio_from_api.clear()
        st.session_state.last_refresh = datetime.now()
        st.rerun()

    # Alerts section
    st.sidebar.divider()
    st.sidebar.subheader("Price Alerts")

    with st.sidebar.expander("Add New Alert", expanded=False):
        ticker_options = portfolio["ticker"].tolist() if not portfolio.empty else []

        if ticker_options:
            alert_ticker = st.selectbox("Ticker", ticker_options)
            alert_type = st.selectbox(
                "Alert Type",
                options=list(AlertType),
                format_func=format_alert_type
            )
            alert_threshold = st.number_input(
                "Threshold",
                min_value=0.0,
                step=0.01,
                format="%.2f"
            )

            if st.button("Add Alert"):
                add_alert(alert_ticker, alert_type, alert_threshold)
                flash(f"Alert added for {alert_ticker}")
                st.rerun()

    alerts = get_alerts()
    if alerts:
        st.sidebar.caption(f"{len(alerts)} active alert(s)")
        for alert_id, alert in alerts.items():
            col1, col2 = st.sidebar.columns([3, 1])
            with col1:
                st.caption(f"{'🔔' if alert.triggered else '⏳'} {alert.ticker}: {format_alert_type(alert.alert_type)} {alert.threshold:.2f}")
            with col2:
                if st.button("✕", key=f"del_{alert_id}"):
                    remove_alert(alert_id)
                    st.rerun()


def render_portfolio_summary(portfolio: pd.DataFrame):
    """Render portfolio summary metrics."""
    total_entry = portfolio["entry_value"].sum()
    total_current = portfolio["platform_value"].sum()
    total_pnl = portfolio["platform_profit"].sum()
    total_pnl_pct = (total_pnl / total_entry * 100) if total_entry > 0 else 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Portfolio Value", format_currency(total_current))
    with col2:
        st.metric("Total Cost", format_currency(total_entry))
    with col3:
        st.metric("Total P/L", format_currency(total_pnl), format_change(total_pnl_pct, is_percent=True))
    with col4:
        st.metric("Holdings", len(portfolio))


def render_holdings_table(portfolio: pd.DataFrame):
    """Render the holdings table."""
    st.subheader("Holdings")

    display_df = portfolio[[
        "ticker", "quantity", "entry_price", "platform_price",
        "entry_value", "platform_value", "platform_profit", "platform_growth"
    ]].rename(columns={
        "ticker": "Ticker", "quantity": "Qty", "entry_price": "Entry Price",
        "platform_price": "Current Price", "entry_value": "Entry Value",
        "platform_value": "Current Value", "platform_profit": "P/L",
        "platform_growth": "Growth %",
    })

    # Keep the values numeric and let Streamlit format them: no per-cell
    # Python formatting, and columns still sort numerically when clicked.
    euro = st.column_config.NumberColumn(format="euro")
    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Entry Price": euro,
            "Current Price": euro,
            "Entry Value": euro,
            "Current Value": euro,
            "P/L": euro,
            "Growth %": st.column_config.NumberColumn(format="%+.2f%%"),
        },
    )


@st.fragment
def render_charts_section(portfolio: pd.DataFrame):
    """
    Render the price chart for one selected holding.

    st.tabs runs the code for every tab, so the old version fetched history
    for every ticker on every rerun. Now only the chosen ticker is fetched,
    and as a fragment, changing ticker/period reruns only this section.
    """
    st.subheader("Price Charts")
    st.caption("Historical charts from yfinance")

    yf_by_label = dict(zip(portfolio["ticker"], portfolio["yf_ticker"]))
    if not yf_by_label:
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        label = st.selectbox("Ticker", options=list(yf_by_label), key="chart_ticker")
    with col2:
        period = st.selectbox("Chart Period", options=list(CHART_PERIODS), index=2, key="chart_period")

    ticker = yf_by_label[label]
    chart = create_price_chart(ticker, CHART_PERIODS[period])
    if chart:
        st.plotly_chart(chart, width="stretch")
    else:
        st.warning(f"Unable to load chart data for {label} ({ticker})")


def render_allocation_chart(portfolio: pd.DataFrame):
    """Render portfolio allocation pie chart."""
    st.subheader("Portfolio Allocation")

    fig = px.pie(
        portfolio,
        values="platform_value",
        names="ticker",
        title="Current Value Distribution",
        hole=0.4,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=400)

    st.plotly_chart(fig, width="stretch")


def render_import_export_section(portfolio: pd.DataFrame):
    """Render import/export controls."""
    st.subheader("Import / Export")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Import Portfolio**")
        uploaded_portfolio = st.file_uploader(
            "Upload portfolio Excel file",
            type=["xlsx", "xls"],
            key="portfolio_upload"
        )

        if uploaded_portfolio is not None:
            if st.button("Import Portfolio", key="import_portfolio_btn"):
                success, message, _ = import_portfolio_excel(uploaded_portfolio, PORTFOLIO_FILE)
                if success:
                    flash(message)
                    st.rerun()
                else:
                    st.error(message)

        st.markdown("**Import Trades**")
        uploaded_trades = st.file_uploader(
            "Upload trades Excel file",
            type=["xlsx", "xls"],
            key="trades_upload"
        )

        if uploaded_trades is not None:
            merge_trades = st.checkbox("Merge with existing trades", value=True)
            if st.button("Import Trades", key="import_trades_btn"):
                success, message, _ = import_trades_excel(uploaded_trades, TRADES_FILE, merge=merge_trades)
                if success:
                    flash(message)
                    st.rerun()
                else:
                    st.error(message)

    with col2:
        st.markdown("**Export Data**")

        # Export portfolio
        if not portfolio.empty:
            # A callable is only run when the button is clicked, so the
            # Excel file is no longer rebuilt on every rerun.
            st.download_button(
                label="Download Portfolio Excel",
                data=lambda: export_portfolio_excel(portfolio),
                on_click="ignore",
                file_name=f"portfolio_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # Export trades
        trades_df = get_trades()
        if not trades_df.empty:
            st.download_button(
                label="Download Trades Excel",
                data=lambda: export_trades_excel(trades_df),
                on_click="ignore",
                file_name=f"trades_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # File info
        st.markdown("**Current Files**")
        portfolio_info = get_file_info(PORTFOLIO_FILE)
        trades_info = get_file_info(TRADES_FILE)

        if portfolio_info:
            st.caption(f"Portfolio: {portfolio_info['name']} ({portfolio_info['size']:,} bytes)")
            st.caption(f"Modified: {portfolio_info['modified'].strftime('%Y-%m-%d %H:%M')}")

        if trades_info:
            st.caption(f"Trades: {trades_info['name']} ({trades_info['size']:,} bytes)")
            st.caption(f"Modified: {trades_info['modified'].strftime('%Y-%m-%d %H:%M')}")


def render_trades_tab():
    """Render the Trades tab content."""
    st.header("Trade History")

    trades_df = get_trades()

    if trades_df.empty:
        st.info("No trades found. Import trades from Excel or add manually.")
    else:
        # Summary metrics
        summary = get_trades_summary(trades_df)
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Trades", summary["total_trades"])
        with col2:
            st.metric("Buys / Sells", f"{summary['total_buys']} / {summary['total_sells']}")
        with col3:
            st.metric("Total Volume", format_currency(summary["total_volume"]))
        with col4:
            st.metric("Total Fees", format_currency(summary["total_fees"]))

        st.divider()

        # Filters
        col1, col2, col3 = st.columns(3)

        with col1:
            tickers = ["All"] + sorted(trades_df["ticker"].unique().tolist())
            selected_ticker = st.selectbox("Filter by Ticker", tickers)

        with col2:
            directions = ["All", "buy", "sell"]
            selected_direction = st.selectbox("Filter by Direction", directions)

        with col3:
            date_range = st.date_input(
                "Date Range",
                value=(trades_df["timestamp"].min().date(), trades_df["timestamp"].max().date()),
                key="trades_date_range"
            )

        # Apply filters
        filtered_df = trades_df.copy()

        if selected_ticker != "All":
            filtered_df = filtered_df[filtered_df["ticker"] == selected_ticker]

        if selected_direction != "All":
            filtered_df = filtered_df[filtered_df["direction"] == selected_direction]

        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = filtered_df[
                (filtered_df["timestamp"].dt.date >= start_date) &
                (filtered_df["timestamp"].dt.date <= end_date)
            ]

        # Display trades table
        st.subheader(f"Trades ({len(filtered_df)})")

        display_df = filtered_df[[
            "timestamp", "ticker", "direction", "price", "quantity", "amount", "fee"
        ]].copy()
        display_df.columns = ["Time", "Ticker", "Direction", "Price", "Qty", "Amount", "Fee"]
        display_df["Direction"] = display_df["Direction"].str.upper()

        euro = st.column_config.NumberColumn(format="euro")
        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                "Price": euro,
                "Amount": euro,
                "Fee": euro,
            },
        )

        # Trade volume chart
        st.subheader("Trade Activity")

        if not filtered_df.empty:
            # Group by date
            daily_volume = filtered_df.groupby(filtered_df["timestamp"].dt.date).agg({
                "amount": "sum",
                "trade_id": "count"
            }).reset_index()
            daily_volume.columns = ["Date", "Volume", "Trades"]

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=daily_volume["Date"],
                y=daily_volume["Volume"],
                name="Volume",
                marker_color="steelblue"
            ))

            fig.update_layout(
                title="Daily Trading Volume",
                xaxis_title="Date",
                yaxis_title="Volume (EUR)",
                height=300
            )

            st.plotly_chart(fig, width="stretch")

    # Add new trade section
    st.divider()
    st.subheader("Add New Trade")

    with st.form("add_trade_form"):
        col1, col2, col3 = st.columns(3)

        with col1:
            new_ticker = st.text_input("Ticker", placeholder="e.g., VWCE.EU")
            new_direction = st.selectbox("Direction", ["buy", "sell"])

        with col2:
            new_price = st.number_input("Price", min_value=0.0, step=0.01, format="%.2f")
            new_quantity = st.number_input("Quantity", min_value=1, step=1)

        with col3:
            new_fee = st.number_input("Fee", min_value=0.0, step=0.01, format="%.2f", value=0.0)
            new_date = st.date_input("Date", value=datetime.now().date())
            new_time = st.time_input("Time", value=datetime.now().time())

        submitted = st.form_submit_button("Add Trade")

        if submitted:
            if new_ticker and new_price > 0 and new_quantity > 0:
                trade_datetime = datetime.combine(new_date, new_time)
                updated_df = add_trade(
                    trades_df,
                    ticker=new_ticker.upper(),
                    direction=new_direction,
                    price=new_price,
                    quantity=new_quantity,
                    fee=new_fee,
                    timestamp=trade_datetime
                )

                if save_trades(updated_df):
                    flash(f"Trade added: {new_direction.upper()} {new_quantity} {new_ticker} @ {format_currency(new_price)}")
                    st.rerun()
                else:
                    st.error("Failed to save trade")
            else:
                st.error("Please fill in all required fields (Ticker, Price, Quantity)")


def render_live_portfolio():
    """
    Summary metrics, holdings table and allocation chart.

    Called as a fragment with run_every when auto-refresh is on: Streamlit
    re-executes only this function on a timer, so the live numbers update
    without rerunning (and redrawing) the rest of the page.
    """
    live = st.session_state.data_source == "api" and API_AVAILABLE

    if live and st.session_state.auto_refresh:
        elapsed = (datetime.now() - st.session_state.last_refresh).total_seconds()
        # Small tolerance: a timer tick can land a few ms before the interval
        if elapsed >= st.session_state.refresh_interval - 1:
            fetch_portfolio_from_api.clear()
            st.session_state.last_refresh = datetime.now()

    try:
        portfolio, data_source, warning = load_portfolio_data()
    except Exception:
        return  # main() already reported the error

    if warning:
        st.warning(warning)
    elif live:
        st.success(f"📡 {data_source}")
    else:
        st.info(f"📄 {data_source}")

    if portfolio.empty:
        return

    render_portfolio_summary(portfolio)

    st.divider()

    col1, col2 = st.columns([2, 1])
    with col1:
        render_holdings_table(portfolio)
    with col2:
        render_allocation_chart(portfolio)

    if live:
        st.caption(f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")


def render_portfolio_tab(portfolio: pd.DataFrame):
    """Render the Portfolio tab content."""
    auto = (st.session_state.data_source == "api" and API_AVAILABLE
            and st.session_state.auto_refresh)
    run_every = st.session_state.refresh_interval if auto else None

    # st.fragment can wrap a function at call time, which lets the interval
    # come from the sidebar setting.
    st.fragment(render_live_portfolio, run_every=run_every)()

    st.divider()

    render_charts_section(portfolio)


def main():
    """Main application entry point."""
    st.title("Portfolio Monitor")
    show_flash()

    # Load portfolio data (cached) for the sidebar and import/export tab
    try:
        portfolio, _, _ = load_portfolio_data()
    except FileNotFoundError:
        portfolio = pd.DataFrame()
        st.warning(f"Portfolio file not found: {PORTFOLIO_FILE}")
    except Exception as e:
        portfolio = pd.DataFrame()
        st.error(f"Error loading portfolio: {e}")

    render_sidebar(portfolio)

    tab_portfolio, tab_trades, tab_import_export = st.tabs(["📊 Portfolio", "📈 Trades", "📁 Import/Export"])

    with tab_portfolio:
        if not portfolio.empty:
            render_portfolio_tab(portfolio)
        else:
            st.info("No portfolio data. Import a portfolio Excel file in the Import/Export tab.")

    with tab_trades:
        render_trades_tab()

    with tab_import_export:
        render_import_export_section(portfolio)


if __name__ == "__main__":
    main()
