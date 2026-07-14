FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt

CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
