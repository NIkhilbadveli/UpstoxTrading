from datetime import datetime

import upstox_client
import webbrowser
import pandas as pd

# Replace with your Upstox API credentials
API_KEY = "c0147464-89c2-4b2c-9f8a-132f9e105027"
API_SECRET = "c7r53ceqzb"


def login_to_upstox(code):
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
        "redirect_uri": "https://google.co.in/",
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
        print(f"An unexpected error occurred: {e}")
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
            print(f"Order rejected for {order_status_raw["trading_symbol"]}: {order_status_message}")
            return None
        return api_response
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


def buy_shares(symbol, quantity, order_type="MARKET", price=0, product_type="D"):
    """Buys shares."""
    instrument = get_instrument_by_symbol(symbol)
    if instrument:
        transaction_type_enum = "BUY"
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


def get_last_traded_price(symbol):
    """Fetches the last traded price for a given symbol."""
    instrument = get_instrument_by_symbol(symbol)
    try:
        api_client = get_upstox_client()
        quotes_api = upstox_client.MarketQuoteApi(api_client)
        quote_data = quotes_api.ltp(instrument, "api-version-2")
        return quote_data.to_dict()["data"][f"NSE_EQ:{symbol}"]["last_price"]
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


def exit_all_positions():
    """Exits all open positions."""
    try:
        exited_positions = []
        for position in get_current_positions():
            if position["sell_price"] > 0:
                continue
            sell_shares(position["trading_symbol"], position["quantity"])
            exited_positions.append(position["trading_symbol"])
        print(f"All positions exited - {exited_positions}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def get_current_positions():
    """Fetches the current positions."""
    try:
        api_client = get_upstox_client()
        positions_api = upstox_client.PortfolioApi(api_client)
        positions_data = positions_api.get_positions(api_version="v2")
        return positions_data.to_dict()["data"]
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


if __name__ == "__main__":
    login_to_upstox()
    try:
        print("Starting trading...")
        exit_all_positions()
        # print(get_current_positions())
        # print(get_balance())
        # buy_order = buy_shares("OLAELEC", 1)
        # if buy_order:
        #     print("Buy order details:", buy_order)
        # sell_order = sell_shares("OLAELEC", 1)
        # if sell_order:
        #     print("Sell order details:", sell_order)
    except Exception as e:
        print(f"Main program error: {e}")
