# ARG PYTHON_VERSION="3.11"
# FROM python:${PYTHON_VERSION}-alpine AS base

FROM alexxit/go2rtc

WORKDIR /app
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

COPY *.py ./
RUN chmod a+x ./spawn.py

ENTRYPOINT ["/sbin/tini", "--"]
CMD [ "/app/spawn.py" ]

EXPOSE 1984/tcp
EXPOSE 8554/tcp
EXPOSE 8555/tcp
EXPOSE 8555/udp
