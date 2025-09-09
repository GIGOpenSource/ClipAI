class DisableCSRFMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, callback, callback_args, callback_kwargs):
        # Disable CSRF checks for all requests (API only project)
        setattr(request, '_dont_enforce_csrf_checks', True)
        return None


