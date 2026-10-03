import os

# Starlette's TestClient sends Host: testserver, which a deployment .env allowlist will reject.
os.environ.setdefault("TRUSTED_HOSTS", "testserver,localhost,127.0.0.1")
if "testserver" not in os.environ["TRUSTED_HOSTS"].split(","):
    os.environ["TRUSTED_HOSTS"] = "testserver," + os.environ["TRUSTED_HOSTS"]
