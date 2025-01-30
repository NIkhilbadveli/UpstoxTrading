import threading
from datetime import datetime
import pytz
import yfinance as yf
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor
import logging
from upstox_utils import (
    buy_shares,
    get_balance,
    get_current_positions,
    get_current_holdings, sell_shares,
)

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

MAX_STOCKS_TO_BUY = 3
STOP_LOSS = 3  # In % from today's high
IST = pytz.timezone("Asia/Kolkata")

stocks_already_bought = []
promising_stocks = []  # List of promising stocks (up by 5% or more)


def get_data(ticker, period="1d", interval="1m"):
    try:
        data = ticker.history(
            period=period,
            interval=interval,
        )
    except Exception as e:
        data = pd.DataFrame()
    return data


def get_yesterday_close_price(ticker):
    data = get_data(ticker, period="5d", interval="1d")
    if data.empty or data.shape[0] < 2:
        return 0
    return data["Close"].iloc[-2]


# Reusable function for monitoring a single ticker
def monitor_ticker(ticker_symbol):
    global stocks_already_bought
    ticker = yf.Ticker(ticker_symbol)
    promising = False
    data = get_data(ticker)
    opening_price = get_yesterday_close_price(ticker)
    if data.empty or opening_price == 0:
        return promising
    last_price = data["High"].iloc[-1]
    percent_change = (last_price - opening_price) / opening_price * 100
    if (
            percent_change >= 18
            and len(stocks_already_bought) <= MAX_STOCKS_TO_BUY
            and ticker_symbol.replace(".NS", "") not in stocks_already_bought
    ):
        # Ensure amount_per_trade stays between 7500 and 100000
        amount_per_trade = max(0.30 * get_balance() / 2, 7500)
        amount_per_trade = min(amount_per_trade, 100000)
        # Calculate quantity based on last_price and amount_per_trade
        quantity = amount_per_trade // last_price
        buy_order_details = buy_shares(ticker_symbol.replace(".NS", ""), quantity)
        if buy_order_details:
            print(f"Bought {quantity} shares of {ticker_symbol} at {last_price}")
            stocks_already_bought.append(ticker_symbol.replace(".NS", ""))

    elif percent_change >= 5:
        promising = True

    return promising


# Function to update promising stocks list
def update_promising_stocks(tickers):
    global promising_stocks
    promising_stocks = []  # Reset the list of promising stocks
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(monitor_ticker, tickers))
    # Store only those tickers that are promising
    promising_stocks = [ticker for ticker, is_promising in zip(tickers, results) if is_promising]
    print(f"Promising stocks updated: {promising_stocks}")


# Bigger function that uses threading to monitor multiple tickers
def monitor_tickers(tickers):
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(monitor_ticker, tickers))
    return results


def update_nse_tickers_list():
    from requests import Session

    # Initialize a session to maintain cookies
    s = Session()

    # Update session headers to emulate a browser
    s.headers.update(
        {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36"
        }
    )

    try:
        # Step 1: Get the cookies from the main NSE website
        s.get("https://www.nseindia.com/")

        # Step 2: Download the CSV file from the provided URL
        nse_tickers_url = (
            "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
        )
        response = s.get(nse_tickers_url)

        # Step 3: Check if the response is successful
        if response.status_code == 200:
            # Step 4: Save the content to a file, overwriting an existing file
            with open("nse_tickers.csv", "wb") as f:
                f.write(response.content)
            print("File downloaded and saved as 'nse_tickers.csv'")
        else:
            print(
                f"Failed to download the file. HTTP status code: {response.status_code}"
            )

    except Exception as e:
        print(f"An error occurred: {e}")


# Main function to handle time-based phase execution
def start_monitoring(nse_tickers):
    wait_time = 30
    last_update_time = None

    while True:
        current_time = datetime.now(IST).time()

        # Update promising stocks every 30 minutes (if within trading hours)
        if (
                datetime.strptime("09:15", "%H:%M").time()
                <= current_time
                < datetime.strptime("15:30", "%H:%M").time()
        ):
            if last_update_time is None or (datetime.now() - last_update_time).seconds >= 1800:
                print("Updating promising stocks list...")
                update_promising_stocks(nse_tickers)
                last_update_time = datetime.now()

            # Monitor only the promising stocks
            print("\nPhase 1: Monitoring promising tickers: ", datetime.now(IST))
            monitor_tickers(promising_stocks)

        else:
            if current_time < datetime.strptime("09:15", "%H:%M").time():
                print("Before 9:15 AM. Waiting for the market to open...")
                time.sleep(wait_time)
            else:
                print("Outside trading hours. Try after 9:15 AM tomorrow...")
                break

        print("Sleeping for 30 seconds...")
        time.sleep(wait_time)


def auto_sell_if_stop_loss_hit():
    """Take already bought stocks list and sell if stop loss is hit by calculating the loss from today's high"""
    for position in get_current_positions():
        if position["quantity"] <= 0:
            continue
        stock = position["trading_symbol"]
        ticker = yf.Ticker(f"{stock}.NS")
        data = get_data(ticker)
        today_high = get_data(ticker, interval="1d", period="5d")["High"].iloc[-1]
        if data.empty:
            continue
        last_price = data["High"].iloc[-1]
        percent_change = (last_price - today_high) / today_high * 100
        if percent_change <= -STOP_LOSS:
            sell_order_details = sell_shares(stock, position["quantity"])
            if sell_order_details:
                print(f"Sold {position["quantity"]} shares of {stock} at {last_price}")


def run_stop_loss_check():
    while True:
        auto_sell_if_stop_loss_hit()
        time.sleep(180)


def run_start_monitoring(stock_symbols):
    start_monitoring(stock_symbols)


def do_live_trading():
    global stocks_already_bought, promising_stocks
    update_nse_tickers_list()

    # Read the NSE tickers from the CSV file
    tickers_df = pd.read_csv("nse_tickers.csv")
    stock_symbols = (
        tickers_df.query("` SERIES` == 'EQ'")["SYMBOL"]
        .apply(lambda x: f"{x}.NS")
        .tolist()
    )

    # Current positions only applies to intraday, they become holdings by next morning
    current_positions = get_current_positions()
    if current_positions:
        stocks_already_bought = [
            position["trading_symbol"]
            for position in current_positions
            if position["quantity"] > 0
        ]

    current_holdings = get_current_holdings()
    if current_holdings:
        # cnc_used_quantity represents quantity of holdings blocked towards an open/completed order
        stocks_already_bought.extend(
            [
                holding["trading_symbol"]
                for holding in current_holdings
                if holding["quantity"] > 0 and holding["cnc_used_quantity"] == 0
            ]
        )

    print(f"Already bought stocks: {stocks_already_bought}")

    monitoring_thread = threading.Thread(target=run_start_monitoring, args=(stock_symbols,))
    monitoring_thread.start()

    stop_loss_thread = threading.Thread(target=run_stop_loss_check)
    stop_loss_thread.start()

do_live_trading()
