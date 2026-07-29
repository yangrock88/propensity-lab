FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy the full project
COPY . .

# Install all dependencies into the project venv
RUN uv sync --frozen

# Port HF Spaces expects
ENV PORT=7860
EXPOSE 7860

# startup.sh: run the pipeline once, then serve the dashboard
CMD ["bash", "startup.sh"]
