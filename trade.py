


class Trade:
    def __init__(self, broker, ticker, quantity, price, trade_type, date):
        self.broker = broker
        self.ticker = ticker
        self.quantity = quantity
        self.price = price
        self.trade_type = trade_type  # 'buy' or 'sell'
        self.date = date

    def get_trade_info(self):
        return {
            "Broker": self.broker,
            "Ticker": self.ticker,
            "Quantity": self.quantity,
            "Price": self.price,
            "Trade Type": self.trade_type,
            "Date": self.date
        }
    def __str__(self):
        return f"Trade({self.broker}, {self.ticker}, {self.quantity}, {self.price}, {self.trade_type}, {self.date})"
    def __repr__(self):
        return self.__str__()
    def __eq__(self, other):
        if not isinstance(other, Trade):
            return False
        return (self.broker == other.broker and
                self.ticker == other.ticker and
                self.quantity == other.quantity and
                self.price == other.price and
                self.trade_type == other.trade_type and
                self.date == other.date)
    def __hash__(self):
        return hash((self.broker, self.ticker, self.quantity, self.price, self.trade_type, self.date))
    def to_dict(self):
        return {
            "broker": self.broker,
            "ticker": self.ticker,
            "quantity": self.quantity,
            "price": self.price,
            "trade_type": self.trade_type,
            "date": self.date
        }
    @classmethod
    def from_dict(cls, trade_dict):
        return cls(
            broker=trade_dict["broker"],
            ticker=trade_dict["ticker"],
            quantity=trade_dict["quantity"],
            price=trade_dict["price"],
            trade_type=trade_dict["trade_type"],
            date=trade_dict["date"]
        )
    





class Trades:
    def __init__(self):
        self.trades = []
        self.concatenated_trades = {}

    def add_trade(self, trade: Trade):
        self.trades.append(trade)
        
    def update_live_book(self, trade : Trade):
        """Update the book with a new trade."""
        if trade not in self.trades:
            self.concatenated_trades[trade.ticker] = {"quantity": trade.quantity, "price": trade.price, "broker": trade.broker}
        else:
            to_update_trade = self.get_trade_by_ticker_book(trade.ticker)
            if trade.trade_type == 'buy':
                to_update_trade.quantity += trade.quantity
            #for the moment not allowed to sell more than you have, to be short
            elif trade.trade_type == 'sell':
                if to_update_trade.quantity < trade.quantity:
                    raise ValueError("Cannot sell more than you have in the book.")
                to_update_trade.quantity -= trade.quantity
            self.concatenated_trades[trade.ticker] = to_update_trade
            
                

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
