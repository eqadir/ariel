FROM python:3.12-bookworm

WORKDIR /ariel

RUN apt-get -y update && apt-get -y upgrade && apt-get install -y --no-install-recommends ffmpeg

COPY requirements.txt .
RUN pip3 install -r ./requirements.txt

COPY app.py .

# Service must listen to $PORT environment variable.
# This default value facilitates local development.
ENV PORT 8080

# Run the web service on container startup.
# CMD exec gunicorn -b :$PORT app:app
CMD [ "python" , "app.py" ]
