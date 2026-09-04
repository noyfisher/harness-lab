# Agent image: Epoch AI's arm64 SWE-bench instance image + Node 22 + pinned Claude Code.
# Build: docker build --build-arg INSTANCE_ID=<id> -t harness-lab/agent.arm64.<id> -f bench/docker/Dockerfile bench/docker
ARG INSTANCE_ID=django__django-11099
FROM ghcr.io/epoch-research/swe-bench.eval.arm64.${INSTANCE_ID}
ARG NODE_VERSION=22.20.0
ARG CLAUDE_VERSION=2.1.76
RUN set -eux; \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.xz" -o /tmp/node.tar.xz; \
    mkdir -p /opt/node; tar -xJf /tmp/node.tar.xz -C /opt/node --strip-components=1; rm /tmp/node.tar.xz
ENV PATH=/opt/node/bin:$PATH
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_VERSION}" && claude --version
RUN mkdir -p /harness /task/repro
ENV DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    CLAUDE_CONFIG_DIR=/harness
WORKDIR /testbed
