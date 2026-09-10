FROM python:3.11-slim

# Instalacja ffmpeg oraz nodejs (niezbędnych do przetwarzania audio i rozwiązywania skryptów YouTube)
RUN apt-get update && \
    apt-get install -y ffmpeg nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Najpierw kopiujemy requirements i instalujemy je by wykorzystać cache dockera
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiowanie reszty plików bota
COPY . .

CMD ["python", "main.py"]
