#!/bin/bash

# Exit on error
set -e

echo "Building and deploying SAM application..."
sam build
sam deploy --guided

echo "Deployment complete!"
