ARG BUILD_FROM
FROM ${BUILD_FROM}

WORKDIR /opt/drink-tracker

COPY app /opt/drink-tracker/app
COPY pyproject.toml /opt/drink-tracker/pyproject.toml
COPY rootfs /

RUN pip install --no-cache-dir /opt/drink-tracker

RUN chmod a+x /etc/services.d/drink-tracker/run /usr/local/bin/start-drink-tracker.sh

