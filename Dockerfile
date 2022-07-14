FROM python:3.9

WORKDIR /raindropiobot

RUN apt install -y libpango-1.0-0 libpangoft2-1.0-0

COPY requirements.txt .
RUN pip install -r requirements.txt

ENV PYTHONPATH "${PYTHONPATH}:/raindropiobot"
COPY . /raindropiobot/

CMD ["python", "src/main.py"]
