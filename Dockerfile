FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN apt-get update && apt-get install -y bash

EXPOSE 9000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "9000"]
