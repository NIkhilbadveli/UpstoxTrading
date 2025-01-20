from datetime import datetime

import yfinance as yf
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor
import logging
from upstox_utils import (
    login_to_upstox,
    buy_shares,
    get_balance,
    exit_all_positions,
    get_current_positions
)

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)


stocks_already_bought = []


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
    ticker = yf.Ticker(ticker_symbol)
    promising = False
    data = get_data(ticker)
    opening_price = get_yesterday_close_price(ticker)
    if data.empty or opening_price == 0:
        return promising
    last_price = data["High"].iloc[-1]
    percent_change = (last_price - opening_price) / opening_price * 100
    if percent_change >= 18 and ticker_symbol not in stocks_already_bought:
        # Ensure amount_per_trade stays between 15000 and 100000
        amount_per_trade = max(0.3 * get_balance(), 15000)
        amount_per_trade = min(amount_per_trade, 100000)
        # Calculate quantity based on last_price and amount_per_trade
        quantity = amount_per_trade // last_price
        buy_order_details = buy_shares(ticker_symbol.replace(".NS", ""), quantity)
        if buy_order_details:
            print(f"Bought {quantity} shares of {ticker_symbol} at {last_price}")
            stocks_already_bought.append(ticker_symbol)

    elif percent_change >= 5:
        promising = True

    return promising


# Bigger function that uses threading to monitor multiple tickers
def monitor_tickers(tickers):
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(monitor_ticker, tickers))
    return results


# Main function to handle time-based phase execution
def start_monitoring(nse_tickers):
    promising_stocks = []
    while True:
        current_time = datetime.now().time()
        if (
            datetime.strptime("09:15", "%H:%M").time()
            <= current_time
            < datetime.strptime("10:15", "%H:%M").time()
        ):
            print("\nPhase 1: Monitoring all tickers: ", datetime.now())
            wait_time = 30
            monitor_tickers(nse_tickers)
        elif (
            datetime.strptime("10:15", "%H:%M").time()
            <= current_time
            < datetime.strptime("15:30", "%H:%M").time()
        ):
            print("\nPhase 2: Monitoring promising tickers: ", datetime.now())
            wait_time = 60

            try:
                # Get promising stocks from the file if the date is the same
                with open("promising_stocks.txt", "r") as f:
                    promising_stocks_date, *promising_stocks = f.read().splitlines()
                if promising_stocks_date == datetime.now().strftime("%Y-%m-%d"):
                    print(f"Promising stocks found: {promising_stocks}")
                else:
                    promising_stocks = []
            except FileNotFoundError:
                promising_stocks = []

            # Find promising tickers by monitoring if promising_stocks is empty
            if not promising_stocks:
                promising_results = monitor_tickers(nse_tickers)
                promising_stocks = [
                    nse_tickers[i]
                    for i, is_promising in enumerate(promising_results)
                    if is_promising
                ]
                # Save these promising stocks to a file
                with open("promising_stocks.txt", "w") as f:
                    f.write(f"{datetime.now().strftime('%Y-%m-%d')}\n{'\n'.join(promising_stocks)}")
                print(f"Promising stocks found: {promising_stocks}")
            else:
                # Now monitor only the promising tickers
                monitor_tickers(promising_stocks)
        else:
            print("Outside trading hours. Try after 9:15 AM tomorrow...")
            break

        print("Sleeping for 1 minute...")
        time.sleep(wait_time)  # Sleep for a minute before checking the time again


def do_live_trading():
    global stocks_already_bought

    # Read the NSE tickers from the CSV file
    tickers_df = pd.read_csv("nse_tickers.csv")
    stock_symbols = [symbol + ".NS" for symbol in tickers_df["Symbol"].tolist()]

    # Update stocks already bought
    current_positions = get_current_positions()
    if current_positions:
        stocks_already_bought = [position["trading_symbol"] for position in current_positions
                                 if position["sell_price"] == 0]
        print(f"Already bought stocks: {stocks_already_bought}")

    start_monitoring(stock_symbols)


if __name__ == "__main__":
    # bse_tickers_df = pd.read_csv("bse_tickers.csv")
    # stock_symbols = [
    #     symbol + ".BO" for symbol in bse_tickers_df["Security Id"].tolist()
    # ]

    do_live_trading()
