FROM python:3.9

WORKDIR /raindropiobot

COPY requirements.txt .
RUN pip install -r requirements.txt

ENV PYTHONPATH "${PYTHONPATH}:/raindropiobot"
COPY . /raindropiobot/

CMD ["python", "src/main.py"]
