from django.urls import path

from . import console, views

urlpatterns = [
    path("health/", views.health),
    path("talks/", views.talk_list),
    path("talks/<int:issue>/", views.talk_detail),
    path("signups/", views.signup),
    path("feed/", views.feed_list),
    path("feed/<int:pk>/", views.feed_detail),
    path("ingest/", views.ingest),
    path("signin-sheets/", views.signin_sheet),
    path("otis/kb/", views.otis_kb),
    path("otis/config/", views.otis_config),
    path("weather/", views.weather),
    path("suggestions/", views.suggestion),
    path("episodes/", views.episode_list),
    path("episodes/<int:number>/", views.episode_detail),
    path("content-version/", console.public_content_version),
    # Local content console (Bearer CONSOLE_KEY)
    path("console/overview/", console.overview),
    path("console/talks/", console.talks),
    path("console/talks/<int:issue>/", console.talk),
    path("console/talks/<int:issue>/push/", console.talk_push),
    path("console/talks/<int:issue>/spanish-draft/", console.talk_spanish_draft),
    path("console/feed/", console.feed),
    path("console/feed/<int:pk>/", console.feed_item),
    path("console/feed/<int:pk>/push/", console.feed_push),
    path("console/episodes/", console.episodes),
    path("console/episodes/<int:number>/", console.episode),
    path("console/episodes/<int:number>/push/", console.episode_push),
    path("console/kb/", console.kb),
    path("console/kb/<int:pk>/", console.kb_entry),
    path("console/suggestions/", console.suggestions),
    path("console/suggestions/<int:pk>/", console.suggestion),
    path("console/broadcast/", console.broadcast),
]
