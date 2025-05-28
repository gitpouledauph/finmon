import os
import pandas as pd


### Regiustered brokers will be in a csv file abd will be loadedau fur et à mesure et création si besoin

TradeRepublic = {"Name": "TradeRepublic",
                 "Floating Fees": "fees",
                 "Fixed Fees": "fixed_fees",
                 "PEA": False,
                "Currency": "currency",
                "Country": "country",
                "Website": "website",
                }

Binance = {"Name": "Binance",
                 "Floating Fees": "fees",
                 "Fixed Fees": "fixed_fees",
                 "PEA": False,
                "Currency": "currency",
                "Country": "country",
                "Website": "website",
                }

Revolut = {"Name": "Revolut",
                 "Floating Fees": "fees",
                 "Fixed Fees": "fixed_fees",
                 "PEA": False,
                "Currency": "currency",
                "Country": "country",
                "Website": "website",
                }

IBKR = {"Name": "IBKR",
                 "Floating Fees": "fees",
                 "Fixed Fees": "fixed_fees",
                 "PEA": False,
                "Currency": "currency",
                "Country": "country",
                "Website": "website",
                }

Boursorama = {"Name": "Boursorama",
                 "Floating Fees": "fees",
                 "Fixed Fees": "fixed_fees",
                 "PEA": True,
                "Currency": "currency",
                "Country": "country",
                "Website": "website",
                }


registered_brokers = {"Boursorama": Boursorama,
                    "IBKR" : IBKR,
                    "Revolut" : Revolut, 
                    "Binance" : Binance, 
                    "TradeRepublic" : TradeRepublic}

class Broker:
    def __init__(self, broker_name, floating_fees: float = None, fixed_fees : float = None, PEA : bool = None, currency : str = None, country : str = None, website : str = None):
        """Initialize a Broker instance."""
        self.broker = broker_name
        self.is_registered = False
        self.floating_fees = floating_fees
        self.fixed_fees = fixed_fees
        self.PEA = PEA
        self.currency = currency
        self.country = country
        self.website = website
        self.compute_broker_infos()
    

    def is_registered(self):
        """Check if the broker is registered."""
        path = "/Users/me/Desktop/Monitoring_Investments/Registered Brokers"
        # check if self.broker.csv exists in the path
        if not os.path.exists(path):
            raise FileNotFoundError(f"The path {path} does not exist.")
        try:

            self.broker_infos = pd.read_csv(os.path.join(path, f"{self.broker}.csv"))
            self.is_registered = True
            print(f"Broker {self.broker} is registered. Adding the broker's info to the code")
        except FileNotFoundError:
            print(f"Broker {self.broker} is not registered. Adding the broker to the system")
        
    def compute_broker_infos(self):
        if self.is_registered():
            self.floating_fees = self.broker_infos[self.broker]["Floating Fees"]
            self.fixed_fees = self.broker_infos[self.broker]["Fixed Fees"]
            self.PEA = self.broker_infos[self.broker]["PEA"]
            self.currency = self.broker_infos[self.broker]["Currency"]
            self.country = self.broker_infos[self.broker]["Country"]
            self.website = self.broker_infos[self.broker]["Website"]
        else:
             self.add_broker()
            


    def add_broker(self):
        """Add a broker to the system."""
        dico_broker = {"Name": self.broker,
                        "Floating Fees": self.floating_fees,
                        "Fixed Fees": self.fixed_fees,
                        "PEA": self.PEA,
                        "Currency": self.currency,
                        "Country": self.country,
                        "Website": self.website,
                        }
        path = "/Users/me/Desktop/Monitoring_Investments/Registered Brokers"
        dico_broker.to_csv(os.path.join(path, f"{self.broker}.csv"))

    def get_floating_fees(self):
        """Get the floating fees associated with a broker."""
        return self.floating_fees
    
    
    def get_fixed_fees(self):
        """Get the fixed fees associated with a broker."""
        return self.fixed_fees
    
    def get_pea(self):
        """Get the PEA status of a broker."""
        return self.PEA
    
    def get_currency(self):
        """Get the currency of a broker."""
        return self.currency
    
    def get_country(self):
        """Get the country of a broker."""
        return self.country
    
    def get_website(self):
        """Get the website of a broker."""
        return self.website

    def get_broker(self):
        """Get a specific broker."""
        return self.broker
    
    def get_broker_info(self):
        """Get all the information associated with a broker."""
        return {
            "Name": self.broker,
            "Floating Fees": self.floating_fees,
            "Fixed Fees": self.fixed_fees,
            "PEA": self.PEA,
            "Currency": self.currency,
            "Country": self.country,
            "Website": self.website
        }  

    




c
    
