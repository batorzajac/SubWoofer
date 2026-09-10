FROM python:3.11-slim

# Instalacja ffmpeg, nodejs oraz deno (niezbędnych do przetwarzania audio i wyzwań JS YouTube)
RUN apt-get update && \
    apt-get install -y ffmpeg nodejs curl unzip && \
    curl -fsSL https://deno.land/install.sh | sh && \
    mv /root/.deno/bin/deno /usr/local/bin/deno && \
    rm -rf /root/.deno && \
    apt-get purge -y curl unzip && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Najpierw kopiujemy requirements i instalujemy je by wykorzystać cache dockera
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiowanie reszty plików bota
COPY . .

CMD ["python", "main.py"]
