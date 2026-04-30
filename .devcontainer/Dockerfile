FROM mcr.microsoft.com/devcontainers/python:1-3.11-bullseye

ENV PYTHONUNBUFFERED 1

# Remove broken yarn repository and install system dependencies
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# [Optional] Set the default user to vscode
USER vscode






