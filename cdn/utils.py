from django.conf import settings
from pathlib import Path

def get_project_name():
    root_urlconf = settings.ROOT_URLCONF
    project_name = root_urlconf.split('.')[0]  # Get the first part before the dot
    return project_name


def generate_path(model):
    service_name = get_project_name().lower()
    app_name = model.__class__._meta.app_label.lower()
    model_name = model.__class__.__name__.lower()
    model_pk = str(model.id)

    path = Path(service_name) / app_name / model_name / model_pk

    return service_name, app_name, model_name, model_pk, path
