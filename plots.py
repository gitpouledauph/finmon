
######################################################

#################### IMPORTS ########################

#####################################################


import maplotlib.pyplot as plt
from trade import Trade, Trades
from pnl import PnL
import pandas as pd 



######################################################

#################### Plot CLASS ######################

#####################################################

csv_path = ""

class Plot:
    def __init__(self, csv_path=csv_path):
        self.csv_path = csv_path

    def get_df(self):
        self.df = pd.read_csv(self.csv_path)

    def get_cash_column(self):
        self.cash_column = self.df["Cash Value"]

    def get_date_column(self):
        pass

    def get_unrealized_pnl_column(self):
        pass

    def get_book_value_column(self):
        pass
    
    def get_realized_pnl_column(self):
        pass

    def get_full_ptf_column(self):
        pass

    
    def __identify_column(self, column):
        column = column.lower()
        if "cash" in column:
            col = self.get_cash_column()
        elif "unrealized" in column:
            col = self.get_unrealized_pnl_column()
        elif "realized" in column: 
            col = self.get_realized_pnl_column()
        elif "book" in column:
            col = self.get_book_value_column()
        elif "full" in column:
            col = self.get_full_ptf_column()
        return col
    

    def plot_single_column(self, column):
        col = self.__identify_column(column)

        dates = self.get_date_column()
        plt.plot(dates, col, label=column)
        plt.xlabel("Dates")
        plt.ylabel(column)
        plt.show()

    def plot_multiple_columns(self, column_lists):
        col_lst = []

        for column in column_lists:
            col_lst.append(self.__identify_column(column))
        
        dates = self.get_date_column()

        for col, label in zip(col_lst, column_lists):
            plt.plot(dates, col, label=label)
        
        plt.xlabel("Dates")
        plt.show()



