from pathlib import Path

from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.contrib.auth import get_user_model
from django.db.models.signals import class_prepared
from django.utils import timezone
from django.apps import apps

from .client import CDNClient
from .managers import SoftDeleteManager
from .utils import get_project_name

User = get_user_model()


class File(models.Model):
    uuid = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    name = models.CharField(max_length=128)
    size = models.FloatField(null=True, blank=True)
    type = models.CharField(max_length=256)
    version = models.TextField(null=True, blank=True)
    url = models.URLField(max_length=256, null=True, blank=True)
    user = models.ForeignKey(User, related_name='cdn_files', on_delete=models.DO_NOTHING)
    is_assigned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    last_temp_path = models.CharField(max_length=128, null=True, blank=True)

    objects = SoftDeleteManager()

    def save(self, *args, force_insert=False, force_update=False, using=None, update_fields=None):
        created = self.pk is None
        if created:

            client = CDNClient()

            result = client.check_file_status(uuid=str(self.uuid))
            if not result["isAvailable"]:
                raise Exception("File Not Found!")
            meta_data = client.get_file_metadata(uuid=str(self.uuid))

            file_user = User.objects.get(id=int(meta_data['userId']))
            if self.user.id != file_user.id:
                raise Exception("Not Same Users")
            self.name = meta_data['fileName']
            self.url = meta_data['fileUrl']
            self.size = meta_data['fileSize']
            self.type = meta_data['fileType']

        super().save(
            *args,
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            # update_fields=list(update_fields)
        )

    def assign_to_path(self, path: str, service_name: str, app_name: str, model_name: str):
        client = CDNClient()
        result = client.set_to_path(str(self.uuid), path, service_name, app_name, model_name)

        if result:
            self.url = result.get('newUrl')
            self.uuid = result.get('newUuid')
            self.version = result.get('version')
            print(self.url)
            self.is_assigned = True
            self.save(update_fields=['is_assigned', 'file', 'uuid', 'version'])
            return result

    def get_metadata(self):
        client = CDNClient()
        result = client.get_file_metadata(str(self.uuid))
        if result:
            return result

    def get_file(self, output_path: Path = None) -> str:
        if self.last_temp_path and Path(self.last_temp_path).exists():
            return self.last_temp_path
        else:
            self.last_temp_path = None

        if output_path:
            output_path = output_path / self.name
        client = CDNClient()
        result = client.download_file(str(self.uuid), output_file_path=output_path, file_name=self.name)
        self.last_temp_path = result
        self.save(update_fields=['last_temp_path'])
        return result

    def delete(self, using=None, keep_parents=False, hard_delete=False):
        self.deleted_at = timezone.now()
        client = CDNClient()
        result = client.delete_file(str(self.uuid), hard_delete=hard_delete)
        if not result['isDone']:
            raise Exception(f'failed to delete file, {result["message"]}')
        return self.save(update_fields=['deleted_at'])

    def hard_delete(self, using=None, keep_parents=False):
        return self.delete(using=using, keep_parents=keep_parents, hard_delete=True)


class FileAssociationMixin:

    @classmethod
    def _add_files_field(cls, model_cls):
        """Add the `files` GenericRelation field to the model."""
        if not issubclass(model_cls, models.Model):
            raise TypeError("FileAssociationMixin can only be used with Django model classes.")

        if not hasattr(model_cls, 'files'):
            # Use a lazy reference for the File model
            def lazy_generic_relation():
                return GenericRelation(
                    File,
                    related_name=f'{model_cls.__name__.lower()}_files'
                )

            # Add the field to the class
            model_cls.add_to_class('files', lazy_generic_relation())

    @classmethod
    def handle_class_prepared(cls, sender, **kwargs):
        """Handle the `class_prepared` signal to add the files field."""
        if issubclass(sender, cls):
            cls._add_files_field(sender)

    def __init_subclass__(cls, **kwargs):
        """Connect the class_prepared signal for subclasses."""
        super().__init_subclass__(**kwargs)
        class_prepared.connect(cls.handle_class_prepared, sender=cls)

    def add_file(self, uuid):  # requested_user
        from pathlib import Path  # Ensure it's imported locally
        # Ensure that _meta and app_label are accessible
        if not hasattr(self.__class__, '_meta'):
            raise TypeError("FileAssociationMixin can only be used with Django model classes.")

        app_name = self.__class__._meta.app_label.lower()
        service_name = get_project_name().lower()
        model_name = self.__class__.__name__.lower()
        path = Path(service_name) / app_name / model_name

        # Fetch the user and associate the file
        u1 = User.objects.get(id=1)  # Replace this with your user-fetching logic
        file = File.objects.create(uuid=uuid, user=u1, content_object=self)
        result = file.assign_to_path(
            path=str(path),
            service_name=service_name,
            app_name=app_name,
            model_name=model_name,
        )

        return result

    def delete_file(self, uuid: str, hard_delete: bool = False):
        try:
            file = self.files.get(uuid=uuid)
            return file.hard_delete() if hard_delete else file.delete()

        except File.DoesNotExist as err:
            return err
