######################################################

#################### IMPORTS ########################

#####################################################


from trade import Trade, Trades
import pandas as pd 
import os

######################################################

#################### PNL CLASS ######################

#####################################################

'''

The goal of this file is to build tools to compute
realized and unrealized pnl at everytime (in absolute
and percentages)

'''



class PnL:
    def __init__(self, book : Trades, date: str):
        self.book_object = book
        self.book = self.book_object.concatenated_trades
        self.trades = self.book_object.trades
        self.unrealized_pnl = 0
        self.realized_pnl = 0
        self.pos_abs_pnl_dic = {a:0 for a in self.book.keys()}
        self.pos_rel_pnl_dic = {a:0 for a in self.book.keys()}
        self.unrealized_pnl = 0
        self.pnl_date = date



    def compute_realized_pnl(self):
        self.realized_pnl = 0
        for trade in self.trades:
            if trade.trade_type == 'sell':
                self.realized_pnl += trade.pnl
    

    def compute_unrealized_pnl(self):
        for ticker, pos in self.book.items():
            live_value = 1 #to update with a live retriever such as yfinance
            pos_pnl = pos['quantity'] *(live_value - pos['price'])
            self.pos_abs_pnl_dic[ticker] = pos_pnl
            self.unrealized_pnl += pos_pnl
            self.pos_rel_pnl_dic[ticker] = pos_pnl/ (pos['price'] * pos['quantity']) if pos['price'] * pos['quantity'] != 0 else 0

    def get_pos_value(self):
        for ticker, pos in self.book.items():
            live_value = 1 #to update with a live retriever such as yfinance using self.pnl_date
            pos_value = pos['quantity']*live_value
        return pos_value

    
    def get_portfolio_value(self):
        return self.get_available_cash() + self.get_pos_value()
    
    def get_full_pnl(self):
        return self.get_unrealized_pnl() + self.get_realized_pnl()


    def get_available_cash(self):
        return self.book_object.get_cash()

    def get_unrealized_pnl(self):
        self.compute_unrealized_pnl()
        return self.unrealized_pnl
    

    def get_realized_pnl(self):
        self.compute_realized_pnl()
        return self.realized_pnl
    

    def book_to_logs(self):
        dico = {
            "Date": self.pnl_date,
            "Cash Value": self.get_available_cash(),
            "Realized Pnl": self.realized_pnl,
            "Unrealized PnL": self.unrealized_pnl,
            "Book Value": self.get_pos_value(),
            "Full PnL": self.get_full_pnl(),
            }

        return dico

    def pos_to_logs(self):
        dico = {
            "Pos Abs PnL": self.pos_abs_pnl_dic,
            "Pos Rel PnL": self.pos_rel_pnl_dic,
            }

        return dico
    
    def export_to_csv(self, path="/Users/me/Desktop/Monitoring_Investments/book.csv"):
        # Export book_to_logs
        new_book_df = pd.DataFrame([self.book_to_logs()])
        if os.path.exists(path):
            existing_book_df = pd.read_csv(path)
            combined_book_df = pd.concat([existing_book_df, new_book_df], ignore_index=True)
        else:
            combined_book_df = new_book_df
        combined_book_df.to_csv(path, index=False)

        # Export pos_to_logs
        pos_path = path.replace(".csv", "_pos.csv")
        new_pos_df = pd.DataFrame([self.pos_to_logs()])
        if os.path.exists(pos_path):
            existing_pos_df = pd.read_csv(pos_path)
            combined_pos_df = pd.concat([existing_pos_df, new_pos_df], ignore_index=True)
        else:
            combined_pos_df = new_pos_df
        combined_pos_df.to_csv(pos_path, index=False)
