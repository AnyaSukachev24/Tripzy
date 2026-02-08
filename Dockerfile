# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
# If requirements.txt doesn't exist, we install manually for now but user should create it.
RUN pip install --no-cache-dir fastapi uvicorn langgraph langchain-google-genai langchain-community duckduckgo-search pinecone-client python-dotenv

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable
ENV NAME World

# Run app.main when the container launches
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
