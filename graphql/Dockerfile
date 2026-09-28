FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY uptime_graphql/ /app/uptime_graphql/

RUN useradd --system --uid 10001 app
USER app

EXPOSE 8080

CMD ["uvicorn", "--factory", "uptime_graphql.app:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--no-access-log"]
