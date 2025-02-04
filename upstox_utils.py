from datetime import datetime, timedelta
from typing import List, Union, Optional, Dict
from time import sleep
import pytz
import upstox_client
import webbrowser
import pandas as pd

# Replace with your Upstox API credentials
API_KEY = "c0147464-89c2-4b2c-9f8a-132f9e105027"
API_SECRET = "c7r53ceqzb"
IST = pytz.timezone("Asia/Kolkata")
holidays_df = pd.read_csv('market_holidays.csv')
holidays = set(pd.to_datetime(holidays_df["Date"]).dt.date)

current_positions_api_client = None


def login_to_upstox_using_code(code):
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open("login_data.txt", "r") as f:
            last_login_date, access_token = f.read().strip().split(",")
    except (FileNotFoundError, ValueError):
        last_login_date, access_token = "", ""

    if last_login_date == today:
        print("Already logged in today.")
        return access_token

    access_token = get_and_save_access_token(code)

    # Save the current date and access token to the file
    with open("login_data.txt", "w") as f:
        f.write(f"{today},{access_token}")


def get_upstox_client():
    """Initializes and returns an Upstox API client."""
    configuration = upstox_client.Configuration()
    try:
        with open("login_data.txt", "r") as f:
            _, access_token = f.read().strip().split(",")
    except (FileNotFoundError, ValueError):
        raise Exception("Access token not found. Please login first.")
    configuration.access_token = access_token
    return upstox_client.ApiClient(configuration)


def get_and_save_access_token(code):
    """Retrieves Upstox access token. MUST BE IMPLEMENTED SECURELY."""
    import requests

    url = "https://api.upstox.com/v2/login/authorization/token"

    payload = {
        "code": code,
        "client_id": API_KEY,
        "client_secret": API_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": "https://httpbin.org/get",
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    return response.json()["access_token"]


def get_instrument_by_symbol(symbol):
    """Fetches instrument details for a given symbol."""
    try:
        upstox_nse = pd.read_csv("Upstox_NSE.csv")
        # find the row "trading_symbol" == symbol
        row = upstox_nse.loc[upstox_nse["tradingsymbol"] == symbol]
        if row.empty:
            print(f"Symbol {symbol} not found in the Upstox NSE list.")
            return None
        return row["instrument_key"].iloc[0]
    except Exception as e:
        print(f"An unexpected error occurred in get_instrument_by_symbol: {e}")
        return None


def place_order(
        transaction_type, instrument, quantity, order_type, product_type, price=None
):
    """Places an order."""
    try:
        api_client = get_upstox_client()
        orders_api = upstox_client.OrderApi(api_client)
        order_data = upstox_client.PlaceOrderRequest(
            transaction_type=transaction_type,
            instrument_token=instrument,
            quantity=quantity,
            order_type=order_type,
            product=product_type,
            price=price,
            validity="DAY",
            disclosed_quantity=quantity,
            is_amo=False,
            trigger_price=0,
        )
        api_response = orders_api.place_order(order_data, api_version="v2")

        order_status_raw = orders_api.get_order_status(
            order_id=api_response.to_dict()["data"]["order_id"]
        ).to_dict()["data"]
        order_status = order_status_raw["status"]
        order_status_message = order_status_raw["status_message"]
        if order_status == "rejected":
            trading_symbol = order_status_raw["trading_symbol"]
            print(f"Order rejected for {trading_symbol}: {order_status_message}")
            return None
        return api_response
    except Exception as e:
        print(f"An unexpected error occurred in place_order: {e}")
        return None


def buy_shares(symbol, quantity, order_type="MARKET", price=0, product_type="D"):
    """Buys shares."""
    instrument = get_instrument_by_symbol(symbol)
    if instrument:
        transaction_type_enum = "BUY"
        print(f"Trying to buy {quantity} shares of {symbol}...")
        return place_order(
            transaction_type_enum,
            instrument,
            quantity,
            order_type,
            product_type,
            price,
        )
    return None


def sell_shares(symbol, quantity, order_type="MARKET", price=0, product_type="D"):
    """Sells shares."""
    instrument = get_instrument_by_symbol(symbol)
    if instrument:
        transaction_type_enum = "SELL"
        return place_order(
            transaction_type_enum,
            instrument,
            quantity,
            order_type,
            product_type,
            price,
        )
    return None


def get_balance():
    """Fetches the account balance."""
    try:
        api_client = get_upstox_client()
        balance_api = upstox_client.UserApi(api_client)
        balance_data = balance_api.get_user_fund_margin("api_version", segment="SEC")
        return balance_data.to_dict()["data"]["equity"]["available_margin"]
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


def get_last_traded_price(symbols, instrument_keys):
    """Fetches the last traded price for a given symbol."""
    instrument = ",".join(instrument_keys)

    try:
        api_client = get_upstox_client()
        quotes_api = upstox_client.MarketQuoteApi(api_client)
        quote_data = quotes_api.ltp(instrument, "api-version-2")
        return {s: quote_data.to_dict()["data"][f"NSE_EQ:{s}"]["last_price"] for s in symbols}
    except Exception as e:
        print(f"An unexpected error occurred in get_last_traded_price: {e}")
        return None


def get_ohlc_data(symbols, instrument_keys):
    def chunks(lst, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    ohlc_data = {}
    try:
        api_client = get_upstox_client()
        quotes_api = upstox_client.MarketQuoteApi(api_client)

        for symbol_chunk, key_chunk in zip(chunks(symbols, 500), chunks(instrument_keys, 500)):
            instrument = ",".join(key_chunk)
            quote_data = quotes_api.get_market_quote_ohlc(instrument, interval="1d", api_version="v2")
            quote_data_dict = quote_data.to_dict()["data"]
            for s in symbol_chunk:
                try:
                    ohlc_data[s] = {
                        "ltp": quote_data_dict[f"NSE_EQ:{s}"]["last_price"],
                        "high": quote_data_dict[f"NSE_EQ:{s}"]["ohlc"]["high"]
                    }
                except KeyError:
                    print(f"OHLC Data not found for {s}")
                    ohlc_data[s] = None
        return ohlc_data
    except Exception as e:
        print(f"An unexpected error occurred in get_ohlc_data: {e}")
        return None


def get_last_trading_date():
    instrument = "NSE_EQ|INE062A01020"  # for SBIN
    today = datetime.now(IST).date()
    from_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    try:
        api_client = get_upstox_client()
        quotes_api = upstox_client.HistoryApi(api_client)
        quote_data = quotes_api.get_historical_candle_data1(instrument, interval="day", from_date=from_date,
                                                            to_date=to_date, api_version="v2")
        quote_data_dict = quote_data.to_dict()["data"]
        trading_dates = [datetime.strptime(candle[0], "%Y-%m-%dT%H:%M:%S%z").date() for candle in
                         quote_data_dict['candles']]
        trading_dates = [date for date in trading_dates if date != today]
        last_trading_date = max(trading_dates) if trading_dates else None
    except Exception as e:
        print(f"An unexpected error occurred in get_last_trading_date: {e}")
        last_trading_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Last trading date: {last_trading_date}")
    return last_trading_date


def get_previous_close_price(symbols, instrument_keys):
    """Fetches the previous trading day close price for a given symbol."""
    last_trading_date = get_last_trading_date()
    from_date = (last_trading_date - timedelta(days=5)).strftime("%Y-%m-%d")
    to_date = last_trading_date.strftime("%Y-%m-%d")

    try:
        api_client = get_upstox_client()
        quotes_api = upstox_client.HistoryApi(api_client)
        output = {}
        for s, instrument in zip(symbols, instrument_keys):
            try:
                quote_data = quotes_api.get_historical_candle_data1(instrument, interval="day", from_date=from_date,
                                                                    to_date=to_date, api_version="v2")
                quote_data_dict = quote_data.to_dict()["data"]
                output[s] = quote_data_dict['candles'][0][4]
            except Exception as e:
                print(f"Data not found for {s} on {last_trading_date}")
                output[s] = None
            sleep(0.1)
        return output
    except Exception as e:
        print(f"An unexpected error occurred in get_previous_close_price: {e}")
        return None


def get_open_orders(transaction_type="BUY"):
    """Fetches all open orders."""
    try:
        api_client = get_upstox_client()
        orders_api = upstox_client.OrderApi(api_client)
        orders_data = orders_api.get_order_book(api_version="v2")
        # filter for status = "open" and transaction_type
        filtered_orders = []
        for order in orders_data.to_dict()["data"]:
            if order["status"] == "open" and order["transaction_type"] == transaction_type:
                filtered_orders.append(order["trading_symbol"].replace("-EQ", ""))
        return filtered_orders
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


def exit_all_positions():
    """Exits all open positions."""
    try:
        exited_positions = []
        for position in get_current_positions():
            if position["quantity"] > 0:
                sell_shares(position["trading_symbol"], position["quantity"])
                exited_positions.append(position["trading_symbol"])

        current_holdings = get_current_holdings()
        for holding in current_holdings:
            if holding["quantity"] > 0 and holding["cnc_used_quantity"] == 0:
                sell_shares(holding["trading_symbol"], holding["quantity"])
                exited_positions.append(holding["trading_symbol"])

        print(f"All positions exited - {exited_positions}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def get_current_positions():
    global current_positions_api_client
    try:
        if current_positions_api_client is None:
            current_positions_api_client = get_upstox_client()
        current_positions_api_client = get_upstox_client()
        positions_api = upstox_client.PortfolioApi(current_positions_api_client)
        positions_data = positions_api.get_positions(api_version="v2")
        return positions_data.to_dict()["data"]
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []


def get_current_holdings():
    """Positions become holdings by next day"""
    try:
        api_client = get_upstox_client()
        holdings_api = upstox_client.PortfolioApi(api_client)
        holdings_data = holdings_api.get_holdings(api_version="v2")
        return holdings_data.to_dict()["data"]
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
