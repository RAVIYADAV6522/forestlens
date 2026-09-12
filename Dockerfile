# Hugging Face Space runtime.
#
# Docker, not the Streamlit SDK: Spaces removed the streamlit SDK, and the API now
# accepts only gradio, docker or static. (The Streamlit docs page still describes
# `sdk: streamlit`; it is stale — creating such a Space fails with
# "Invalid option: expected one of gradio|docker|static".)
FROM python:3.12-slim

# git installs sam-2 from source; build-essential covers any C extension fallback.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential \
    && rm -rf /var/lib/apt/lists/*

# Spaces run the container as uid 1000, so everything written at runtime — model
# weights above all — has to live under that user's home or the app dies on a
# read-only path.
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    TORCH_HOME=/home/user/.cache/torch \
    MPLCONFIGDIR=/home/user/.cache/matplotlib \
    PYTHONUNBUFFERED=1 \
    # sam-2 tries to build a CUDA extension by default. It tolerates the failure, but
    # there is no point attempting it on a CPU host.
    SAM2_BUILD_CUDA=0

WORKDIR /home/user/app

COPY --chown=user:user requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user:user . ./

# 7860 is the Spaces default for Docker; app_port in README.md must agree.
EXPOSE 7860

# CORS/XSRF are disabled because Spaces serves the app through a proxy inside an
# iframe, where the default XSRF check breaks the file uploader.
CMD ["streamlit", "run", "app/app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false"]
