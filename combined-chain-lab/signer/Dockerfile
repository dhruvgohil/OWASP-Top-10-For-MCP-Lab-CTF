FROM python:3.11-slim

# Internal-only token signer. No host port is mapped in docker-compose -- it is reachable
# solely over the private lab network (that is what makes the leaked SIGNER_URL the pivot).

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY signer.py token_util.py ./

EXPOSE 9003

CMD ["uvicorn", "signer:app", "--host", "0.0.0.0", "--port", "9003"]
