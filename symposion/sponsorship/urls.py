from django.conf.urls import url
from django.views.generic import TemplateView

from .views import (
    sponsor_apply,
    sponsor_add,
    sponsor_json,
    sponsor_list,
    sponsor_zip_logo_files,
    sponsor_detail
)

urlpatterns = [
    url(r"^$", sponsor_list, name="sponsor_list"),
    url(r"^sponsors.json$", sponsor_json, name="sponsor_json"),
    url(r"^apply/$", sponsor_apply, name="sponsor_apply"),
    url(r"^add/$", sponsor_add, name="sponsor_add"),
    url(r"^ziplogos/$", sponsor_zip_logo_files, name="sponsor_zip_logos"),
    url(r"^(?P<pk>\d+)/$", sponsor_detail, name="sponsor_detail"),
]
