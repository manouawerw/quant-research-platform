import streamlit as st

st.set_page_config(page_title="Quant Research Platform")

st.title("📈 Quant Research Platform")

st.write("Welcome!")

ticker = st.text_input("Enter a stock ticker")

if ticker:
    st.success(f"Analyzing {ticker.upper()}...")
