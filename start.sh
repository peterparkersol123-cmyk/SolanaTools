#!/bin/bash

# Load environment variables from .env file
export $(cat .env | grep -v '^#' | xargs)

# Activate virtual environment
source venv/bin/activate

# Start Flask server
python3 app.py
