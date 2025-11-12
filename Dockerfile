# Указываем базовый образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Обновляем apt-get и устанавливаем системные зависимости
# (build-essential нужен для компиляции некоторых пакетов python, например numpy)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл с зависимостями
COPY requirements.txt requirements.txt

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в рабочую директорию
COPY . .

# Устанавливаем переменные окружения
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Открываем порт 5000
EXPOSE 5000

# --- ИЗМЕНЕНИЕ ЗДЕСЬ ---
# Заменяем "flask run" на "gunicorn"
# Эта команда запускает Gunicorn с 1 воркером eventlet (требуется для SocketIO)
# и привязывает его к порту 5000, слушая все IP-адреса.
# "app:app" - это ссылка на объект 'app' в файле 'app.py'
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5000", "app:app"]