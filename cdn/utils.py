from django.conf import settings


def get_project_name():
    root_urlconf = settings.ROOT_URLCONF
    project_name = root_urlconf.split('.')[0]  # Get the first part before the dot
    return project_name
