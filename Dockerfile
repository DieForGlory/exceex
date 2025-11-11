# 1. Базовый образ (используем slim-версию Python 3.10)
FROM python:3.11-slim

# 2. Установка рабочей директории внутри контейнера
WORKDIR /app

# 3. Копирование и установка зависимостей
# Копируем requirements.txt отдельно, чтобы Docker мог кэшировать этот слой
COPY requirements.txt .

# 4. Установка зависимостей + gunicorn и eventlet
# gunicorn - это production-сервер (вместо 'flask run')
# eventlet - необходим для поддержки Flask-SocketIO
RUN pip install --no-cache-dir -r requirements.txt gunicorn eventlet

# 5. Копирование всего кода проекта в рабочую директорию /app
COPY . .

# 6. Указание команды для запуска
# Мы говорим gunicorn запустить 'app' (переменную) из 'app.py' (файла)
# Используем '--worker-class eventlet' для SocketIO
# Используем порт 5015, как в вашем app.py
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5015", "manage:app"]