from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^get/?$", views.get_app, name="invite-get"),  # with or without the slash, so a hand-typed link works too
]
