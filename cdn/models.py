from pathlib import Path
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings

from .client import CDNClient

SERVICE_NAME = getattr(settings, "SERVICE_NAME")
SUB_SERVICE_NAME = getattr(settings, "SUB_SERVICE_NAME")


class SingleFileAssociationMixin(models.Model):
    file = models.UUIDField(null=True, blank=True)

    _original_file = None

    @property
    def client(self):
        return CDNClient()

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_file = self.file

    def has_file_changed(self):
        return self.file != self._original_file

    def _check_file_status(self, file_id: str):
        result = self.client.check_file_status(uuid=file_id)
        if not result["is_available"]:
            raise Exception("File Not Found!")

    def handle_single_file_change(self, old_file: str, new_file: str):

        print(f"Single file changed from {old_file} to {new_file}")

        content_type = ContentType.objects.get_for_model(self)

        try:

            if old_file:
                print(f"Deleting old file {old_file} from CDN")
                self._check_file_status(file_id=str(old_file))
                self.client.unassign_from_instance(
                    uuid=str(old_file),
                    content_type_id=content_type.id,
                    object_id=self.id)

            if new_file:
                print(f"Fetching new file {new_file} from CDN")
                self._check_file_status(file_id=str(new_file))
                self.client.assign_to_instance(uuid=str(new_file),
                                               content_type_id=content_type.id,
                                               object_id=self.id)

            self._original_file = self.file
        except Exception as err:
            self.file = self._original_file
            print(f"file update unsuccessful, err: {err}")

    def is_file_filled(self):
        return bool(self.file)

    def save(self, *args, **kwargs):
        if self.has_file_changed():
            self.handle_single_file_change(self._original_file, self.file)
        if not self.pk:
            super().save(*args, **kwargs)
            if self.file:
                self.handle_single_file_change("", self.file)
        else:
            super().save(*args, **kwargs)

    def set_file(self, cdn_file_uuid, requested_user_id):
        if self.file:
            raise ValidationError("File already set")
        self.file = cdn_file_uuid
        SingleFileAssociationMixin.save(self, requested_user_id=requested_user_id)

    def remove_file(self, requested_user_id):
        self.file = None
        SingleFileAssociationMixin.save(self, requested_user_id=requested_user_id)

    def get_file_metadata(self):
        return self.client.get_file_metadata(str(self.file))

    def get_file(self, output_path: Path = None) -> str:
        # if self.last_temp_path and Path(self.last_temp_path).exists():
        #     return self.last_temp_path
        # else:
        #     self.last_temp_path = None
        file_name = self.get_file_metadata().get("file_name")
        if output_path:
            output_path = output_path / self.name
        result = self.client.download_file(str(self.file), output_file_path=output_path, file_name=file_name)
        # self.last_temp_path = result
        # self.save(update_fields=['last_temp_path'])
        return result


class MultipleFileAssociationMixin(models.Model):
    files = models.JSONField(default=list, blank=True)

    _original_files = None

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_files = list(self.files) if self.files else []

    def has_files_changed(self):
        """Compare the original files with the current files."""
        return self.files != self._original_files

    def are_files_filled(self):
        """Check if there are any files."""
        return bool(self.files)

    def handle_multiple_files_change(self, old_files, new_files):
        """Handle file changes: additions and removals."""
        old_set = set(old_files or [])
        new_set = set(new_files or [])

        removed = old_set - new_set
        added = new_set - old_set

        # Print out what was added and removed
        print(f"Files removed: {removed}")
        print(f"Files added: {added}")

        # Example actions when files are removed or added
        for file in removed:
            print(f"Deleting removed file {file} from CDN")
            # You would put your CDN deletion logic here

        for file in added:
            print(f"Fetching added file {file} from CDN")
            # You would put your CDN fetching logic here
        self._original_files = list(self.files) if self.files else []

    def validate_unique(self, exclude=None):
        super().validate_unique(exclude)
        if len(self.files) != len(set(self.files)):
            self.files = list(set(self.files))
            raise ValidationError("Files must be unique. Duplicate files found.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.has_files_changed():
            self.handle_multiple_files_change(self._original_files, self.files)

        super().save(*args, **kwargs)

    def add_file(self, cdn_file_uuid):
        self.files.append(cdn_file_uuid)
        self.save()

    def remove_file(self, cdn_file_uuid):
        self.files.pop(self.files.index(cdn_file_uuid))
        self.save()
