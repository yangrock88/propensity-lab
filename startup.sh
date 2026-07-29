#!/bin/bash
# Runs once on container startup: build the data warehouse, train the
# models, publish the artifacts, then start the dashboard server.
# Takes roughly 90 seconds on first boot — subsequent restarts are faster
# because the synthetic panel is cached.
set -e

echo "==> Generating warehouse and training models..."
uv run python scheduler.py

echo "==> Starting dashboard on port ${PORT:-7860}..."
exec uv run python app/app.py
