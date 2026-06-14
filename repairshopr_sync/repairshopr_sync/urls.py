from django.contrib import admin
from django.urls import path
from repairshopr_data.views import health

urlpatterns = [
    path("health", health),
    path("readyz", health),
    path("", admin.site.urls),
]
