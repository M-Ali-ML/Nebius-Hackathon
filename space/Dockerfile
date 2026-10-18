FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates xz-utils libatomic1 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:/home/user/uienv/bin:$PATH HERMES_HOME=/home/user/hermes \
    PYTHONUNBUFFERED=1

# Hermes Agent v0.22.2 (pinned commit), CLI only
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o /tmp/install.sh \
    && bash /tmp/install.sh --non-interactive --skip-browser --skip-computer-use \
       --commit d923a5eb487a17c0a68801bba9ef0f56c81040a8 \
    && hermes --version

WORKDIR /home/user/app
COPY --chown=user pyproject.toml README.md ./
COPY --chown=user src ./src
# tool environment: the project with its pinned dependencies
RUN python -m venv /home/user/toolenv && /home/user/toolenv/bin/pip install --no-cache-dir .
# UI environment
RUN python -m venv /home/user/uienv && /home/user/uienv/bin/pip install --no-cache-dir \
    "gradio==5.9.1" "pydantic==2.10.6" "huggingface-hub<1.0" "httpx>=0.27,<0.29"

COPY --chown=user . .
RUN mkdir -p $HERMES_HOME/plugins $HERMES_HOME/skills/research \
    && cp space/hermes-config.yaml $HERMES_HOME/config.yaml \
    && cp -R integrations/hermes/nemotron-challenge $HERMES_HOME/plugins/ \
    && cp -R integrations/hermes/skills/britannica-compare $HERMES_HOME/skills/research/ \
    && hermes plugins enable nemotron-challenge \
    && hermes plugins doctor integrations/hermes/nemotron-challenge --ci

ENV NEMOTRON_TOOL_CMD=/home/user/toolenv/bin/python
EXPOSE 7860
CMD ["/home/user/uienv/bin/python", "space/app.py"]
