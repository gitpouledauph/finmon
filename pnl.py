######################################################

#################### PNL CLASS ######################

#####################################################

'''

The goal of this file is to build tools to compute
realized and unrealized pnl at everytime (in absolute
and percentages)

'''

from trade import Trade, Trades

class PnL:
    def __init__(self, book : Trades):
        self.book = book.concatenated_trades
        self.trades = book.trades
        self.unrealized_pnl = 0
        self.realized_pnl = 0
        self.pos_abs_pnl_dic = {a:0 for a in self.book.keys()}
        self.pos_rel_pnl_dic = {a:0 for a in self.book.keys()}
        self.unrealized_pnl = 0



    def compute_realized_pnl(self):
        for trade in self.trades:
            if trade.trade_type == 'sell':
                self.realized_pnl += trade.pnl
    

    def compute_unrealized_pnl(self):
        for ticker, pos in self.book.items():
            live_value = 1 #to update with a live retriever such as yfinance
            pos_pnl = pos.quantity *(live_value - pos.price)
            self.pos_abs_pnl_dic[ticker] = pos_pnl
            self.unrealized_pnl += pos_pnl
            self.pos_rel_pnl_dic[ticker] = pos_pnl/ (pos.price * pos.quantity) if pos.price * pos.quantity != 0 else 0

    def get_pos_value(self):
        for ticker, pos in self.book.items():
            live_value = 1 #to update with a live retriever such as yfinance
            pos_value = pos.quantity*live_value
        return pos_value

    
    def get_portfolio_value(self):
        return self.get_available_cash() + self.get_pos_value()
    
    def get_full_pnl(self):
        return self.get_unrealized_pnl() + self.get_realized_pnl()


    def get_available_cash(self):
        return self.book.cash

    def get_unrealized_pnl(self):
        self.compute_unrealized_pnl()
        return self.unrealized_pnl
    

    def get_realized_pnl(self):
        self.compute_realized_pnl()
        return self.realized_pnl

