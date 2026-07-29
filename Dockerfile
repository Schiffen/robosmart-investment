# Hugging Face Spaces removed `sdk: streamlit` — the only options are now
# gradio, docker and static. Streamlit apps deploy via the Docker template, so
# this file is what actually runs the Space.
#
# Python is pinned to 3.12 deliberately: pandas 2.2.3 segfaults on 3.14.

FROM python:3.12-slim

# Spaces run containers as uid 1000. Streamlit needs a writable HOME for its
# config and cache; without a real user it falls back to / and fails to start.
RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Requirements first so dependency layers cache across code-only pushes.
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY --chown=user:user . .

USER user

# 7860 is the Spaces default for docker SDK. Using it means the Space works
# even if app_port in the README front-matter is ever dropped.
EXPOSE 7860

# enableXsrfProtection=false: the Space renders inside an iframe, and XSRF
# protection breaks the portfolio CSV uploader there.
CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false"]
