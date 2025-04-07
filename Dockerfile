# Imagem base Python
FROM python:3.9-slim

# Definir diretório de trabalho
WORKDIR /app

# Copiar arquivos necessários
COPY requirements.txt .
COPY .env .
COPY app.py .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Expor a porta que o Streamlit usa
EXPOSE 8501

# Comando para rodar o app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
