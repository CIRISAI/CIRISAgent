FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Define build arguments
ARG PROFILE_NAME=teacher
ARG MODE_LIST=discord

# Set ARGs as ENV variables to be available to the application and CMD
ENV PROFILE_NAME=${PROFILE_NAME}
ENV MODE_LIST=${MODE_LIST}

# Source the environment variables and run the application
CMD ["/bin/bash", "-c", "python main.py --modes ${MODE_LIST} --profile ${PROFILE_NAME}"]

