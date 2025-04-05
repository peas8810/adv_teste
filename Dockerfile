# Utiliza uma imagem base leve do Python
FROM python:3.9-slim

# Evita a criação de arquivos .pyc e garante output sem buffer
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Define o diretório de trabalho
WORKDIR /app

# Copia o arquivo de requisitos e instala as dependências
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copia o restante do código para o container
COPY . /app/

# Expõe a porta padrão do Streamlit
EXPOSE 8501

# Comando para iniciar a aplicação Streamlit
CMD ["streamlit", "run", "main.py", "--server.enableCORS", "false"]
