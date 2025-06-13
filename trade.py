
######################################################

############# Single Trade CLASS ######################

######################################################

class Trade:
    def __init__(self, broker: str, ticker: str, quantity: float, price: float, trade_type: str, date:str):
        self.broker = broker
        self.ticker = ticker
        self.quantity = quantity
        self.price = price
        self.trade_type = trade_type  # 'buy' or 'sell'
        self.date = date
        self.pnl = - self.quantity*self.price if self.trade_type=='buy' else 0

    def get_trade_info(self):
        return {
            "Broker": self.broker,
            "Ticker": self.ticker,
            "Quantity": self.quantity,
            "Price": self.price,
            "Trade Type": self.trade_type,
            "Date": self.date,
            "PnL": self.pnl
        }
    def __str__(self):
        return f"Trade({self.broker}, {self.ticker}, {self.quantity}, {self.price}, {self.trade_type}, {self.date}, {self.pnl})"
    
    def __repr__(self):
        return self.__str__()
    
    def __eq__(self, other):
        """Test equality of two trades, useful to raise warnings"""
        if not isinstance(other, Trade):
            return False
        return (self.broker == other.broker and
                self.ticker == other.ticker and
                self.quantity == other.quantity and
                self.price == other.price and
                self.trade_type == other.trade_type and
                self.date == other.date)
    
    def __hash__(self):
        return hash((self.broker, self.ticker, self.quantity, self.price, self.trade_type, self.date, self.pnl))
    
    def to_dict(self):
        return {
            "broker": self.broker,
            "ticker": self.ticker,
            "quantity": self.quantity,
            "price": self.price,
            "trade_type": self.trade_type,
            "date": self.date,
            "PnL": self.pnl
        }
    @classmethod
    def from_dict(cls, trade_dict):
        return cls(
            broker=trade_dict["broker"],
            ticker=trade_dict["ticker"],
            quantity=trade_dict["quantity"],
            price=trade_dict["price"],
            trade_type=trade_dict["trade_type"],
            date=trade_dict["date"],
            pnl=trade_dict['PnL']
        )
    



######################################################

############# Multi Trade CLASS ######################

######################################################


class Trades:
    def __init__(self, cash: float):
        self.trades = []
        self.concatenated_trades = {}
        self.cash = cash


    def add_trade_in_list(self, trade: Trade):
        self.trades.append(trade)

    def add_trade_in_concatenated(self, trade : Trade):
        """Add a trade to the concatenated trades dictionary."""
        if trade.ticker in self.concatenated_trades:
            if trade.trade_type == 'buy':
                self.concatenated_trades[trade.ticker]["price"] = (trade.price  * trade.quantity + self.concatenated_trades[trade.ticker]['price']*self.concatenated_trades[trade.ticker]['quantity'])/(trade.quantity+self.concatenated_trades[trade.ticker]['quantity']) #compute the price with the average price

                self.concatenated_trades[trade.ticker]["quantity"] += trade.quantity
            else :
                self.concatenated_trades[trade.ticker]["quantity"] -= trade.quantity
                if self.concatenated_trades[trade.ticker]["quantity"]<0:
                    print("Error in the trade, we can't be short on this ticker")
                #in this case the average buying price is unchanged, to be checked
        else : 
            if trade.trade_type == 'buy':
                self.concatenated_trades[trade.ticker] = {"quantity": trade.quantity, "price": trade.price, "broker": trade.broker}
            else : 
                print("Error in the trade, we can't be short on this ticker")

    def update_book(self, trade : Trade):
        """Update the book with a new trade."""
        if trade.trade_type == "buy":
            self.cash -= trade.quantity*trade.price
        else:
            self.cash += trade.quantity*trade.price
        if self.cash<0:
            print("Issue with cash value. Can't get negative amount of cash")
        self.get_trade_pnl(trade)
        self.add_trade_in_list(trade)
        self.add_trade_in_concatenated(trade) 

    def get_cash(self):
        return self.cash
    
    def get_trade_pnl(self, trade : Trade):
        if trade.trade_type == 'sell':
            trade.pnl = trade.quantity * (trade.price - self.concatenated_trades[trade.ticker]["price"])
        

    def get_trades(self):
        return self.trades
    
    def close_trade(self, trade: Trade):
        if trade in self.trades:
            self.trades.remove(trade)

    def get_trade_by_ticker_book(self, ticker):
        return self.concatenated_trades[ticker] if ticker in self.concatenated_trades else None
    
    def get_trade_by_ticker(self, ticker):
        return [trade for trade in self.trades if trade.ticker == ticker]
    
    def get_trade_by_broker(self, broker):
        return [trade for trade in self.trades if trade.broker == broker]
    
    def get_trade_by_type(self, trade_type):
        return [trade for trade in self.trades if trade.trade_type == trade_type]
    
    def get_trade_by_date(self, date):
        return [trade for trade in self.trades if trade.date == date]
    
    def get_trade_by_price(self, price):
        return [trade for trade in self.trades if trade.price == price]
    
    def get_trade_by_quantity(self, quantity):
        return [trade for trade in self.trades if trade.quantity == quantity]


    def clear_trades(self):
        self.trades = []
