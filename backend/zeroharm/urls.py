from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Zero Harm admin"
admin.site.site_title = "Zero Harm"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("talks.urls")),
]
