FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# Install OS dependencies and create an unprivileged user.
# tesseract-ocr (+ pol/eng language data) is required for OCR of scanned PDF
# attachments; adjust the language packages to match ZENDESK_OCR_LANGUAGES.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        tesseract-ocr \
        tesseract-ocr-pol \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appuser \
    && useradd --system --gid appuser --shell /usr/sbin/nologin appuser

COPY pyproject.toml requirements.lock README.md /app/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.lock \
    && rm -rf /root/.cache

COPY src /app/src

RUN pip install --no-cache-dir --no-deps .

# Drop privileges for the runtime container
USER appuser

# Default command – expects Zendesk credentials via environment variables or an --env-file
CMD ["zendesk"]
