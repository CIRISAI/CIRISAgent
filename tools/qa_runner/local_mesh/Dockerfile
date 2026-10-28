# One node of the local mesh: the agent and its folded ciris-server node, in a
# network namespace of its own so two of them can each bind 8080/4242/4243 on
# one machine, both talking to the LIVE canonical exactly as a CI leg does.
#
# Ubuntu 24.04, not python:3.12-slim: ciris-server ships manylinux_2_39 wheels,
# and Debian bookworm's glibc is 2.36.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends python3.12 python3.12-venv ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && python3.12 -m venv /venv
ENV PATH=/venv/bin:$PATH

WORKDIR /app
# Dependencies first, so a code-only change reuses this layer.
COPY requirements.txt /app/requirements.txt
RUN pip install -q -r requirements.txt && pip install -q requests httpx

# A server PRERELEASE replaces the requirements.txt pin when serverwheel/ holds
# one (run.sh downloads it); an empty directory keeps the pin.
COPY serverwheel/ /serverwheel/
RUN set -e; w=$(ls /serverwheel/ciris_server-*manylinux*x86_64.whl 2>/dev/null | head -1 || true); \
    if [ -n "$w" ]; then pip install -q --force-reinstall --no-deps "$w"; fi; \
    python -c "import importlib.metadata as m; print('ciris-server', m.version('ciris-server'))"

COPY . /app
# The agent writes beside its checkout (e.g. `.ciris_keys` in its cwd), as a CI
# leg does from its writable checkout; the container runs as the host user so
# the homes stay readable on the host.
RUN chmod -R a+rwX /app
CMD ["python", "-m", "tools.qa_runner.local_mesh.node_bootstrap"]
