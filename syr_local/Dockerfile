# syntax=docker/dockerfile:1
FROM python:3.13-alpine

# openssl creates the local CA/leaf on first start; tzdata lets the add-on
# read the device's local timestamps in the Home Assistant time zone.
RUN apk add --no-cache openssl tzdata

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY server/ /app/server/

# The device endpoint listens on 8443 inside the container; the Supervisor maps
# host port 443 to it. The state API on 8099 is not published to the host.
EXPOSE 8443 8099

CMD ["python3", "-m", "server"]
