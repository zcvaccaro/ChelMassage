import os

# Render sets the PORT environment variable
port = os.environ.get("PORT", "10000")

# Bind to 0.0.0.0 to expose the server outside the container
bind = f"0.0.0.0:{port}"