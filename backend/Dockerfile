FROM python:3.11-slim
WORKDIR /srv
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
ENV PYTHONPATH=/srv
EXPOSE 8000
# Keys come from the environment (docker run --env-file .env); .env is never baked into the image.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
