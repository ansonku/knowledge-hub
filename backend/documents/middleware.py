from django.http import JsonResponse


class SameOriginApiMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path_info.startswith("/api/"):
            return self.get_response(request)

        if request.headers.get("Sec-Fetch-Site") == "cross-site" or request.headers.get("Origin") == "null":
            response = JsonResponse({"detail": "此 API 僅供本站使用。"}, status=403)
        else:
            response = self.get_response(request)
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response
