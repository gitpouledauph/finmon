import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
from pipeline import PortfolioManager

# Titre de l'application
st.title("📊 Portfolio Monitoring App")

initial_cash = 1000000  # Exemple : 1 million de cash initial
csv_path = "/Users/me/Desktop/Monitoring_Investments/book_pos.csv" 


# Initialisation du portfolio manager
if "pm" not in st.session_state:
    st.session_state.pm = PortfolioManager(initial_cash, csv_path)

pm = st.session_state.pm

# Formulaire pour ajouter un nouveau trade
st.subheader("➕ Ajouter un nouveau trade")
with st.form("new_trade_form"):
    broker = st.selectbox("Broker", ["Degiro", "Boursorama", "Revolut", "Binance"])
    ticker = st.text_input("Ticker", value="AAPL")
    quantity = st.number_input("Quantité", value=10)
    price = st.number_input("Prix", value=100.0)
    trade_type = st.selectbox("Type de trade", ["buy", "sell"])
    submitted = st.form_submit_button("Ajouter le trade")

    if submitted:
        try:
            pm.add_trade(broker=broker, ticker=ticker.upper(), quantity=quantity, price=price, trade_type=trade_type)
            st.success("Trade ajouté avec succès.")
        except Exception as e:
            st.error(f"Erreur lors de l'ajout du trade : {e}")

# Historique des trades
st.subheader("📜 Historique des trades")
if pm.book.trades:
    trades_data = [{
        "Date": t.date,
        "Ticker": t.ticker,
        "Quantity": t.quantity,
        "Price": t.price,
        "Trade Type": t.trade_type,
        "Broker": t.broker,
        "PnL": t.pnl
    } for t in pm.book.trades]

    trades_df = pd.DataFrame(trades_data)
    st.dataframe(trades_df)
else:
    st.write("Aucun trade enregistré pour le moment.")

# Positions en cours
st.subheader("📈 Positions actuelles")
if pm.book.positions:
    positions_df = pd.DataFrame.from_dict(pm.book.positions, orient="index")
    st.dataframe(positions_df)
else:
    st.write("Aucune position ouverte.")

# Graphique PnL cumulé
st.subheader("📊 Évolution du PnL global")
pnl_df = pm.book.daily_pnl
if not pnl_df.empty:
    fig, ax = plt.subplots()
    pnl_df.plot(ax=ax)
    ax.set_title("PnL cumulé par ticker")
    ax.set_xlabel("Date")
    ax.set_ylabel("PnL")
    st.pyplot(fig)
else:
    st.write("Aucune donnée de PnL disponible.")
