import os

# Render sets the PORT environment variable
port = os.environ.get("PORT", "10000")

# Bind to 0.0.0.0 to expose the server outside the container
bind = f"0.0.0.0:{port}"

# Reduce concurrency to stay within memory limits on Render Free/Starter tier.
# 1 worker / 2 threads is significantly safer for memory-intensive apps.
workers = 1
threads = 2

# Increase timeout to prevent workers from being killed during slow API initializations
timeout = 120