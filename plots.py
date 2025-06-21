import matplotlib.pyplot as plt
from trade import Trade, Trades
from pnl import PnL
import pandas as pd

csv_path = ""


class Plot:
    def __init__(self, csv_path=None):
        self.csv_path = csv_path

    def plot_series(self, df, column, title=None):
        import matplotlib.pyplot as plt

        plt.figure(figsize=(10,6))
        plt.plot(df.index, df[column], label=column)
        plt.title(title if title else column)
        plt.xlabel("Date")
        plt.ylabel("PnL")
        plt.legend()
        plt.grid(True)
        plt.show()

    def plot_three_series(self, df, columns, title="PnL Overview"):
        import matplotlib.pyplot as plt

        plt.figure(figsize=(12,8))
        for col in columns:
            if col in df.columns:
                plt.plot(df.index, df[col], label=col)
        plt.title(title)
        plt.xlabel("Date")
        plt.ylabel("PnL")
        plt.legend()
        plt.grid(True)
        plt.show()

class Plots:
    def __init__(self, csv_path=csv_path):
        self.csv_path = csv_path

    def get_df(self):
        self.df = pd.read_csv(self.csv_path)
        self.df["Date"] = pd.to_datetime(self.df["Date"])  # conversion en datetime
        self.df = self.df.sort_values("Date")              # tri croissant

    def get_cash_column(self):
        self.get_df()
        self.cash_column = self.df["Cash Value"]

    def get_date_column(self):
        self.get_df()
        self.date_col = self.df["Date"]

    def get_unrealized_pnl_column(self):
        self.get_df()
        self.unrealized_col = self.df["Unrealized PnL"]

    def get_book_value_column(self):
        self.get_df()
        self.book_col = self.df["Book Value"]
    
    def get_realized_pnl_column(self):
        self.get_df()
        self.realized_col = self.df["Realized Pnl"]

    def get_full_ptf_column(self):
        self.get_df()
        self.full_col = self.df["Full PnL"]

    def __identify_column(self, column):
        column = column.lower()
        if "cash" in column:
            self.get_cash_column()
            col = self.cash_column
        elif "unrealized" in column:
            self.get_unrealized_pnl_column()
            col = self.unrealized_col
        elif "realized" in column: 
            self.get_realized_pnl_column()
            col = self.realized_col
        elif "book" in column:
            self.get_book_value_column()
            col = self.book_col
        elif "full" in column:
            self.get_full_ptf_column()
            col = self.full_col
        return col

    def plot_single_column(self, column):
        col = self.__identify_column(column)
        self.get_date_column()
        dates = self.date_col
        plt.plot(dates, col, label=column)
        plt.xlabel("Date")
        plt.ylabel(column)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.legend()
        plt.show()

    def plot_multiple_columns(self, column_lists):
        col_lst = []
        for column in column_lists:
            col_lst.append(self.__identify_column(column))

        self.get_date_column()
        dates = self.date_col

        for col, label in zip(col_lst, column_lists):
            plt.plot(dates, col, label=label)
        
        plt.xlabel("Date")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.legend()
        plt.show()
