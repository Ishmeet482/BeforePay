class PrivateDemoHeaders:
    """Private API responses/errors must never be shared by a CDN or browser cache."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def private(message):
            if message["type"] == "http.response.start" and scope.get(
                "path", ""
            ).startswith("/api/"):
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower()
                    not in {b"cache-control", b"x-vercel-enable-rewrite-caching"}
                ]
                headers.extend(
                    [
                        (b"cache-control", b"private, no-store"),
                        (b"x-vercel-enable-rewrite-caching", b"0"),
                        (b"vary", b"Cookie, Origin"),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, private)
