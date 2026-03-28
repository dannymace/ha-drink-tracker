ARG BUILD_FROM
FROM ${BUILD_FROM}

WORKDIR /opt/drink-tracker

COPY app /opt/drink-tracker/app
COPY pyproject.toml /opt/drink-tracker/pyproject.toml
COPY run.sh /run.sh

RUN pip install --no-cache-dir /opt/drink-tracker

RUN chmod a+x /run.sh

CMD ["/run.sh"]
