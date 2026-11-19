FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/cache/hf

WORKDIR /app/rag

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch
COPY rag/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY rag .

EXPOSE 8100

CMD ["uvicorn", "servidor:app", "--host", "0.0.0.0", "--port", "8100"]
