from trade import Trade, Trades
from pnl import PnL
from plots import Plot
import datetime

class PortfolioManager:
    def __init__(self, initial_cash: float, csv_path: str):
        self.book = Trades(initial_cash)
        self.csv_path = csv_path

    def add_trade(self, broker: str, ticker: str, quantity: float, price: float, trade_type: str, date: str = None):
        if date is None:
            trade_obj = Trade(broker, ticker, quantity, price, trade_type)
        else:
            trade_obj = Trade(broker, ticker, quantity, price, trade_type, date)
        self.book.update_book(trade_obj)

    def update_and_export_pnl(self, date: str = None):
        if date is None:
            date = datetime.date.today().isoformat()
        pnl_obj = PnL(self.book, date)
        pnl_obj.export_to_csv(self.csv_path)

    def show_plot(self, column: str):
        plotter = Plot(csv_path=self.csv_path)
        plotter.plot_single_column(column)

    def get_positions(self):
        # retourne les positions (consolidées)
        return self.book.positions

    def get_trades(self):
        # retourne la liste de tous les trades
        return self.book.get_trades()
