# Stage 1: Build Stage
FROM python:3.12.4 as build

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    wget \
    curl \
    libffi-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory to /app
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .

# Install Python dependencies into a virtual environment
RUN python -m venv /app/venv && \
    . /app/venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Production Stage
FROM python:3.12.4-slim

# Install only required runtime dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory to /app
WORKDIR /app

# Copy the virtual environment from the build stage
COPY --from=build /app/venv /app/venv

# Copy the application code
COPY . .

# Set the PATH to use the virtual environment
ENV PATH="/app/venv/bin:$PATH"

# Ensure writable permissions for static files directory
RUN mkdir -p /app/static && chmod -R 777 /app/static

# Expose the application port
EXPOSE 8010

# Set the default user to root
USER root

# Run the command to start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--reload"]
