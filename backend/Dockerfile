# Dockerfile for LIDAR Module Backend (Conda/Mamba-based)
# This image uses micromamba to handle complex geospatial dependencies (PDAL, GDAL)
# Build from backend/ dir: docker build -t lidar-backend .

FROM mambaorg/micromamba:1.5-jammy

# Set user for micromamba
USER root

# Install system dependencies needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Switch back to micromamba user
USER $MAMBA_USER

WORKDIR /app

# Copy environment file (paths relative to backend/ build context)
COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /tmp/environment.yml

# Create conda environment with all geospatial dependencies
RUN micromamba install -y -n base -f /tmp/environment.yml && \
    micromamba clean --all --yes

# Activate environment for subsequent commands
ARG MAMBA_DOCKERFILE_ACTIVATE=1

# Copy requirements for pip-only packages (RQ, FastAPI extras, etc.)
COPY --chown=$MAMBA_USER:$MAMBA_USER requirements.txt ./requirements.txt

# Install remaining Python dependencies via pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=$MAMBA_USER:$MAMBA_USER app ./app

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Default command: Run the API server
# For worker, override with: ["python", "-m", "app.worker"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

