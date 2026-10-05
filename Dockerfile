FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt \
        -o /usr/local/share/ca-certificates/russian_trusted_root_ca.crt \
    && curl -fsSL https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt \
        -o /usr/local/share/ca-certificates/russian_trusted_sub_ca.crt \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

EXPOSE 8080

CMD ["python", "bot.py"]
