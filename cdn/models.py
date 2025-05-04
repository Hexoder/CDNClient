from pathlib import Path
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
import uuid
from .utils import InfiniteInt, FileMaxedOutError
from .client import CDNClient

SERVICE_NAME = getattr(settings, "SERVICE_NAME")
SUB_SERVICE_NAME = getattr(settings, "SUB_SERVICE_NAME")


class FileAssociationMixin(models.Model):
    class Meta:
        abstract = True

    @property
    def client(self):
        return CDNClient()

    def _check_file_status(self, file_id: str):
        result = self.client.check_file_status(uuid=file_id)
        if not result["is_available"]:
            raise Exception("File Not Found!")


class SingleFileAssociationMixin(FileAssociationMixin):
    file = models.UUIDField(null=True, blank=True)

    _original_file = None

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_file = self.file

    def has_file_changed(self):
        return self.file != self._original_file

    def is_file_filled(self):
        return bool(self.file)

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

    def save(self, *args, **kwargs):
        if self.has_file_changed():
            self.handle_single_file_change(self._original_file, self.file)
        if not self.pk:
            super().save(*args, **kwargs)
            if self.file:
                self.handle_single_file_change("", self.file)
        else:
            super().save(*args, **kwargs)

    def set_file(self, cdn_file_uuid):
        self.file = cdn_file_uuid
        SingleFileAssociationMixin.save(self)

    def remove_file(self):
        self.file = None
        SingleFileAssociationMixin.save(self)

    def get_file_metadata(self):
        return self.client.get_file_metadata(str(self.file))

    def get_file(self, output_path: Path = None) -> str:
        file_name = self.get_file_metadata().get("file_name")
        if output_path:
            output_path = output_path / self.name
        result = self.client.download_file(str(self.file), output_file_path=output_path, file_name=file_name)
        return result


class MultipleFileAssociationMixin(FileAssociationMixin):
    files = models.JSONField(default=list, blank=True)
    files_local_ids = models.JSONField(default=dict, blank=True)
    last_assigned_id = models.PositiveIntegerField(null=True, blank=True)

    _original_files = None
    _max_allowed_files: int | InfiniteInt = InfiniteInt()

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print(self._max_allowed_files)
        self._original_files = list(self.files) if self.files else []

    def _get_last_assigned_local_id(self) -> int:
        return self.last_assigned_id if self.last_assigned_id else 0

    def _get_local_id_by_cdnfileid(self, cdn_file_id: uuid.UUID) -> int | None:
        for key, value in self.files_local_ids.items():
            if value == cdn_file_id:
                return int(key)
        return None

    def _get_cdnfileid_by_local_id(self, local_id: int) -> uuid.UUID | None:
        return self.files_local_ids.get(str(local_id), None)

    def _get_next_local_id(self) -> int:
        return self._get_last_assigned_local_id() + 1

    def _assign_local_id(self, cdn_file_id: uuid.uuid4, new_local_id: int) -> None:

        self.files_local_ids[str(new_local_id)] = cdn_file_id
        self.last_assigned_id = new_local_id

    def _delete_local_id(self, local_id: int) -> None:
        del self.files_local_ids[str(local_id)]

    def has_files_changed(self):
        """Compare the original files with the current files."""
        return self.files != self._original_files

    def are_files_filled(self):
        """Check if there are any files."""
        return bool(self.files)

    def handle_multiple_files_change(self, old_files, new_files):
        """Handle file changes: additions and removals."""

        content_type = ContentType.objects.get_for_model(self)

        old_set = set(old_files or [])
        new_set = set(new_files or [])

        removed = old_set - new_set
        added = new_set - old_set

        # Print out what was added and removed
        print(f"Files removed: {removed}")
        print(f"Files added: {added}")

        try:
            for file in removed:
                print(f"Deleting removed file {file} from CDN")
                self._check_file_status(file_id=str(file))
                old_local_id = self._get_local_id_by_cdnfileid(file)
                self.client.unassign_from_instance(
                    uuid=str(file),
                    content_type_id=content_type.id,
                    object_id=self.id,
                    local_id=old_local_id)
                self._delete_local_id(old_local_id)

            for file in added:
                print(f"Fetching added file {file} from CDN")
                self._check_file_status(file_id=str(file))
                new_local_id = self._get_next_local_id()
                self.client.assign_to_instance(uuid=str(file),
                                               content_type_id=content_type.id,
                                               object_id=self.id,
                                               local_id=new_local_id)
                self._assign_local_id(file, new_local_id)

            self._original_files = list(self.files) if self.files else []

        except Exception as err:
            self.files = self._original_files
            print(f"file update unsuccessful, err: {err}")

    def validate_unique(self, exclude=None):
        super().validate_unique(exclude)
        if len(self.files) != len(set(self.files)):
            self.files = list(set(self.files))
            raise ValidationError("Files must be unique. Duplicate files found.")

    def save(self, *args, **kwargs):

        self.full_clean()
        if self.has_files_changed():
            self.handle_multiple_files_change(self._original_files, self.files)
        if not self.pk:
            super().save(*args, **kwargs)
            if self.files:
                self.handle_multiple_files_change({}, self.files)
        else:
            super().save(*args, **kwargs)

    def add_file(self, cdn_file_uuid):
        if not len(self.files) < self._max_allowed_files:
            raise FileMaxedOutError(self._max_allowed_files)
        self.files.append(cdn_file_uuid)
        self.save()

    def remove_file(self, local_file_id: int):
        cdn_file_uuid = self._get_cdnfileid_by_local_id(local_file_id)
        self._remove_file(cdn_file_uuid)

    def _remove_file(self, cdn_file_uuid: uuid.UUID):
        self.files.pop(self.files.index(cdn_file_uuid))
        self.save()

    def get_file_metadata(self, cdn_file_id: uuid.UUID = None, local_file_id: int = None):
        if local_file_id and not cdn_file_id:
            cdn_file_id = self._get_cdnfileid_by_local_id(local_file_id)
        return self.client.get_file_metadata(str(cdn_file_id))

    def get_file(self, cdn_file_id: uuid.UUID = None, local_file_id: int = None, output_path: Path = None) -> str:
        file_name = self.get_file_metadata(cdn_file_id=cdn_file_id, local_file_id=local_file_id).get("file_name")
        if output_path:
            output_path = output_path / self.name
        result = self.client.download_file(str(self.file), output_file_path=output_path, file_name=file_name)
        return result
