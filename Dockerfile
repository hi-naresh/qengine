ARG TEST_BUILD=0
FROM python:3.11-slim-bullseye AS qengine_basic_env
ENV PYTHONUNBUFFERED 1

RUN apt-get update \
    && apt-get -y install git build-essential libssl-dev \
    && apt-get clean \
    && pip install --upgrade pip

RUN pip3 install Cython numpy

# Prepare environment
RUN mkdir /qengine
WORKDIR /qengine

# Install dependencies
COPY requirements.txt /qengine
RUN pip3 install -r requirements.txt

# Build
COPY . /qengine
RUN pip3 install -e .

FROM qengine_basic_env AS qengine_with_test_0
WORKDIR /home

FROM qengine_basic_env AS qengine_with_test_1
RUN pip3 install codecov pytest-cov
ENTRYPOINT pytest --cov=./ # && codecov

FROM qengine_with_test_${TEST_BUILD} AS qengine_final
WORKDIR /qengine
CMD ["uvicorn", "qengine:fastapi_app", "--host", "0.0.0.0", "--port", "8000"]
