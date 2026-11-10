from django.conf import settings


class GhlFrameMiddleware:
    """Lets GoHighLevel show the back office (and, if switched on, the admin) inside its own screen.

    Browsers refuse to frame a page unless it says who may frame it. Only GoHighLevel's domains are allowed, and only
    for these paths; everything else keeps Django's default of no framing at all.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        framed = request.path.startswith("/backoffice/") or (settings.GHL_EMBED_ADMIN and request.path.startswith("/admin/"))
        if framed:
            response.xframe_options_exempt = True
            response["Content-Security-Policy"] = "frame-ancestors " + " ".join(settings.GHL_FRAME_ANCESTORS)
        return response
