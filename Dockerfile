# syntax=docker/dockerfile:1.27
# Single-stage build: develop (devcontainer). A downstream instance adds its
# own builder/runner stages on top of this same base image and
# postCreateCommand structure -- see docs/TEMPLATE.md's "Contents" section.

ARG DEBIAN_VERSION=trixie

# renovate: datasource=github-releases depName=j178/prek
ARG PREK_VERSION=0.5.2

# renovate: datasource=npm depName=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=2.1.263

# renovate: datasource=github-releases depName=edouard-claude/snip
ARG SNIP_VERSION=0.25.1

ARG SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ARG SSL_CERT_DIR=/etc/ssl/certs

########################################
# develop — interactive devcontainer image, based on Microsoft's generic
# base devcontainer image. No language runtime is installed here at all —
# an instance adds its own (Python via uv, Rust via rustup, Go, Node.js,
# OpenTofu/Ansible, ...) on top of this stage, following the same ARG/
# scripts/develop.sh pattern established below.
########################################
FROM mcr.microsoft.com/devcontainers/base:${DEBIAN_VERSION} AS develop
ARG PREK_VERSION
ARG CLAUDE_CODE_VERSION
ARG SNIP_VERSION
ARG SSL_CERT_FILE
ARG SSL_CERT_DIR

ENV SSL_CERT_FILE=${SSL_CERT_FILE} \
    SSL_CERT_DIR=${SSL_CERT_DIR} \
    REQUESTS_CA_BUNDLE=${SSL_CERT_FILE} \
    CURL_CA_BUNDLE=${SSL_CERT_FILE}

COPY scripts/develop.sh /tmp/develop.sh
RUN bash /tmp/develop.sh "$PREK_VERSION" "$CLAUDE_CODE_VERSION" "$SNIP_VERSION"

USER vscode
WORKDIR /workspace
CMD ["sleep", "infinity"]
