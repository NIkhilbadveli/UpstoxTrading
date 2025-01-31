import threading
from datetime import datetime, timedelta
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
    get_current_holdings, sell_shares, get_previous_close_price, get_ohlc_data, get_open_orders,
)
import json

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

MAX_STOCKS_TO_BUY = 3
STOP_LOSS = 3  # In % from today's high
IST = pytz.timezone("Asia/Kolkata")


# Reusable function for monitoring a single ticker
def monitor_tickers(symbols, instrument_keys, prev_close_dict):
    ohlc_data = get_ohlc_data(symbols, instrument_keys)
    for symbol, data in ohlc_data.items():
        opening_price = prev_close_dict[symbol]
        if opening_price is None:
            continue
        last_price = data["ltp"]
        percent_change = (last_price - opening_price) / opening_price * 100
        if percent_change >= 18:
            stocks_already_bought = get_already_bought_stocks()
            open_buy_orders = get_open_orders()
            if (len(stocks_already_bought) <= MAX_STOCKS_TO_BUY
                    and symbol not in stocks_already_bought and symbol not in open_buy_orders):
                # Ensure amount_per_trade stays between 7500 and 100000
                amount_per_trade = max(0.30 * get_balance() / 2, 7500)
                amount_per_trade = min(amount_per_trade, 100000)
                # Calculate quantity based on last_price and amount_per_trade
                quantity = amount_per_trade // last_price
                if quantity == 0:
                    print(f"Skipping {symbol} due to insufficient funds")
                    continue
                buy_order_details = buy_shares(symbol.replace(".NS", ""), quantity)
                if buy_order_details:
                    print(f"Bought {quantity} shares of {symbol} at {last_price}")


# Main function to handle time-based phase execution
def start_monitoring(symbols, instrument_keys):
    wait_time = 60

    prev_close_dict = {}
    try:
        with open(f"previous_close_prices/{datetime.now(IST).date()}.json", "r") as f:
            prev_close_dict = json.load(f)
    except FileNotFoundError:
        print("Previous close prices file not found. Fetching previous close prices...")
        prev_close_dict = get_previous_close_price(symbols, instrument_keys)
        with open(f"previous_close_prices/{datetime.now(IST).date()}.json", "w") as f:
            json.dump(prev_close_dict, f)

    while True:
        current_time = datetime.now(IST).time()
        if (
                datetime.strptime("09:15", "%H:%M").time()
                <= current_time
                < datetime.strptime("15:30", "%H:%M").time()
        ):
            print("\nPhase 1: Monitoring all tickers: ", datetime.now(IST))
            monitor_tickers(symbols, instrument_keys, prev_close_dict)
        else:
            if current_time < datetime.strptime("09:15", "%H:%M").time():
                print("Before 9:15 AM. Waiting for the market to open...")
                time.sleep(wait_time)
            else:
                print("Outside trading hours. Try after 9:15 AM tomorrow...")
                break

        print("Sleeping for 60 seconds...")
        time.sleep(wait_time)


def auto_sell_if_stop_loss_hit(symbols, instrument_keys):
    """Take already bought stocks list and sell if stop loss is hit by calculating the loss from today's high"""
    open_sell_orders = get_open_orders(transaction_type="SELL")
    for position in get_current_positions():
        stock = position["trading_symbol"]
        quantity = position["quantity"]
        index = symbols.index(stock)
        if index == -1 or quantity <= 0 or stock in open_sell_orders:
            continue
        ins_key = instrument_keys[index]
        ohlc = get_ohlc_data([stock], [ins_key])[stock]
        last_price = ohlc["ltp"]
        today_high = ohlc["high"]
        percent_change = (last_price - today_high) / today_high * 100
        if percent_change <= -STOP_LOSS:
            sell_order_details = sell_shares(stock, quantity)
            if sell_order_details:
                print(f"Sold {quantity} shares of {stock} at {last_price}")


def run_stop_loss_check(symbols, instrument_keys):
    while True:
        auto_sell_if_stop_loss_hit(symbols, instrument_keys)
        time.sleep(180)


def do_live_trading():
    upstox_ins_keys = pd.read_csv("Upstox_Instruments_NSE.csv")
    upstox_symbols = upstox_ins_keys["trading_symbol"].tolist()
    upstox_ins_keys = upstox_ins_keys["instrument_key"].tolist()

    stocks_already_bought = get_already_bought_stocks()

    print(f"Already bought stocks: {stocks_already_bought}")

    monitoring_thread = threading.Thread(target=start_monitoring, args=(upstox_symbols, upstox_ins_keys))
    monitoring_thread.start()

    stop_loss_thread = threading.Thread(target=run_stop_loss_check, args=(upstox_symbols, upstox_ins_keys))
    stop_loss_thread.start()


def get_already_bought_stocks():
    stocks_already_bought = []
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
    return stocks_already_bought
