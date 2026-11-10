from django.contrib import admin
from django.urls import include, path

from talks.api_v2 import api as api_v2

admin.site.site_header = "Zero Harm admin"
admin.site.site_title = "Zero Harm"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("backoffice/", include("backoffice.urls")),
    path("api/v2/", api_v2.urls),
    path("api/", include("talks.urls")),
]
