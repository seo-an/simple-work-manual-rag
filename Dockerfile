FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY simple_work_manual_rag ./simple_work_manual_rag
COPY data/sample ./data/sample
RUN mkdir -p /app/runtime
EXPOSE 23232
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "23232"]
