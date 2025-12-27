FROM python:3.11-slim

WORKDIR /app
COPY . /app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["python", "app.py"]
