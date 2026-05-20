FROM python:3.11-slim

WORKDIR /app

# Копируем requirements первым делом для кэширования слоя
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаём папку для постоянных данных (Bothost монтирует volume сюда)
RUN mkdir -p /app/data && chmod 777 /app/data

CMD ["python", "bot.py"]
