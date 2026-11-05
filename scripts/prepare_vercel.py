"""Prepare a non-secret frontend rewrite. Does not invoke Vercel or deploy."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


def configure(document, origin):
    value = urlsplit(origin)
    if (
        value.scheme != "https"
        or not value.hostname
        or value.username
        or value.password
        or value.path
        or value.query
        or value.fragment
        or value.port not in {None, 443}
        or value.hostname in {"localhost", "127.0.0.1", "::1"}
        or value.hostname.endswith(".invalid")
    ):
        raise ValueError(
            "Use only the actual HTTPS backend origin, with no path or credentials"
        )
    document["rewrites"] = [
        {"source": "/api/:path*", "destination": origin + "/api/:path*"}
    ]
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-origin", required=True)
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "frontend/vercel.json"
    try:
        document = configure(json.loads(target.read_text()), args.backend_origin)
    except ValueError:
        parser.error("Invalid backend origin; no configuration changed")
    target.write_text(json.dumps(document, indent=2) + "\n")
    print("Frontend rewrite prepared. No deployment or network request performed.")
