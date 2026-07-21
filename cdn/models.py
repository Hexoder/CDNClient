import random
import uuid
from pathlib import Path
from types import MappingProxyType

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models, transaction

from .client import CDNClient
from .utils import InfiniteInt, FileMaxedOutError


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

    class Meta:
        abstract = True

    # snapshot last-synced state on load (mirrors the multiple mixin)
    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._original_file = instance.file
        return instance

    @property
    def file_detailed(self):
        return self.client.get_file_metadata(str(self.file))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, '_original_file'):
            self._original_file = self.file

    def has_file_changed(self):
        a = str(self.file) if self.file else None
        b = str(self._original_file) if self._original_file else None
        return a != b

    def is_file_filled(self):
        return bool(self.file)

    def hls_status(self):
        return self.client.hls_status(uuid=str(self.file))

    def hls_url(self):
        return self.client.hls_url(uuid=str(self.file))

    def prepare_hls(self):
        return self.client.prepare_hls(uuid=str(self.file))

    def _sync_file_with_cdn(self, old_file, new_file):

        print(f"Single file changed from {old_file} to {new_file}")
        content_type = ContentType.objects.get_for_model(self)

        if old_file:
            self._check_file_status(file_id=str(old_file))
            self.client.unassign_from_instance(
                uuid=str(old_file),
                content_type_id=content_type.id,
                object_id=self.id,
            )

        if new_file:
            self._check_file_status(file_id=str(new_file))
            self.client.assign_to_instance(
                uuid=str(new_file),
                content_type_id=content_type.id,
                object_id=self.id,
            )

        self._original_file = self.file

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new:
                if self.file:
                    self._sync_file_with_cdn(None, self.file)
            elif self.has_file_changed():
                self._sync_file_with_cdn(self._original_file, self.file)

    def set_file(self, cdn_file_uuid):
        self.file = cdn_file_uuid
        self.save()

    def remove_file(self):
        self.file = None
        self.save()

    def get_file_metadata(self):
        if not self.file:
            return None
        return self.client.get_file_metadata(str(self.file))

    def get_file(self, output_dir: Path = None) -> str:
        if not self.file:
            return None
        file_name = self.get_file_metadata().get("file_name")
        return self.client.download_file(
            str(self.file), output_dir=output_dir, file_name=file_name
        )

    def file_url(self, base_url):
        if self.file and (file_data := self.get_file_metadata()):
            return base_url + file_data["file_url"]
        return None


class MultipleFileAssociationMixin(FileAssociationMixin):
    _files = models.JSONField(default=dict, blank=True)

    _original_files = None
    _max_allowed_files: int | InfiniteInt = InfiniteInt()

    class Meta:
        abstract = True

    @property
    def files(self):
        # read-only view: model.files["main"] works, model.files["main"] = x raises
        return MappingProxyType(self._files)

    @property
    def files_detailed(self):
        from .serializers import FileSerializerMixin
        serializer = FileSerializerMixin()
        return serializer._serialize_multiple_files(self._files)

    # snapshot the last-synced state on load
    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._original_files = dict(instance._files or {})
        return instance

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._original_files is None:
            self._original_files = dict(self._files or {})

    def has_files_changed(self):
        return dict(self._original_files or {}) != dict(self.files or {})

    def _get_cdnfileid_by_local_key(self, local_key):
        return self._files.get(local_key)

    def _get_local_key_by_cdn_uuid(self, cdn_uuid):
        for local_key, file_id in self._original_files.items():
            if file_id == cdn_uuid:
                return local_key
        return None

    def hls_status(self, *, uuid=None, local_key=None):
        uuid = uuid or self._get_cdnfileid_by_local_key(local_key)
        if not uuid:
            return "required at least one arg <uuid , local_id>"
        return self.client.hls_status(uuid=str(uuid))

    def hls_url(self, *, uuid=None, local_key=None):
        uuid = uuid or self._get_cdnfileid_by_local_key(local_key)
        if not uuid:
            return None
        return self.client.hls_url(uuid=str(uuid))

    def prepare_hls(self, uuid=None, local_key=None):
        uuid = uuid or self._get_cdnfileid_by_local_key(local_key)
        if not uuid:
            return None
        return self.client.prepare_hls(uuid=str(uuid))

    def _sync_files_with_cdn(self, old_files, new_files):
        """Assign/unassign CDN files based on (local_key -> uuid) diffs."""
        content_type = ContentType.objects.get_for_model(self)
        old = old_files or {}
        new = new_files or {}

        to_unassign = {k: v for k, v in old.items() if new.get(k) != v and v}
        to_assign = {k: v for k, v in new.items() if old.get(k) != v and v}

        print(f"Unassigning: {to_unassign}")
        print(f"Assigning:   {to_assign}")

        for local_key, cdn_uuid in to_unassign.items():
            self._check_file_status(file_id=str(cdn_uuid))
            self.client.unassign_from_instance(
                uuid=str(cdn_uuid),
                content_type_id=content_type.id,
                object_id=self.id,
                local_key=local_key,
            )

        for local_key, cdn_uuid in to_assign.items():
            self._check_file_status(file_id=str(cdn_uuid))
            self.client.assign_to_instance(
                uuid=str(cdn_uuid),
                content_type_id=content_type.id,
                object_id=self.id,
                local_key=local_key,
            )

        self._original_files = dict(new)

    # TODO DEPRECATED, REMOVE IN NEXT VERSION
    # def validate_unique(self, exclude=None):
    #     super().validate_unique(exclude)
    #     values = list(self._files.values())
    #     if len(values) != len(set(values)):
    #         raise ValidationError(
    #             "The same CDN file is assigned to multiple keys."
    #         )

    def save(self, *args, **kwargs):
        self.full_clean(exclude=kwargs.pop("exclude", []))
        is_new = self._state.adding  # capture BEFORE super().save()
        with transaction.atomic():
            super().save(*args, **kwargs)  # save first so self.id exists
            if is_new:
                self._sync_files_with_cdn({}, dict(self.files))
            elif self.has_files_changed():
                self._sync_files_with_cdn(self._original_files, dict(self.files))

    def add_file(self, cdn_file_uuid, local_key=None, replace=False):
        # only a NEW key grows the count; replacing an existing one doesn't
        if local_key and local_key not in self.files and len(self.files) >= self._max_allowed_files:
            raise FileMaxedOutError(self._max_allowed_files)
        if local_key and local_key in self.files and not replace:
            raise FileExistsError(local_key)

        def gen_local_key():
            basename = self.__class__.__name__.lower()
            rand_num = random.randint(0, 100000)
            key = f'{basename}-{rand_num}'
            if key in self.files:
                gen_local_key()
            return key

        existing_key = self._get_local_key_by_cdn_uuid(cdn_file_uuid)
        if existing_key and replace:
            del self._files[existing_key]

        if not local_key:
            local_key = gen_local_key()

        self._files[local_key] = str(cdn_file_uuid)
        self.save()

    def remove_file(self, local_key):
        del self._files[local_key]
        self.save()

    def swap_files(self, local_key1, local_key2):
        self._files[local_key1], self._files[local_key2] = self._files[local_key2], self._files[local_key1]
        self.save()

    def change_key(self, old_key, new_key):
        file_uuid = self._files[old_key]
        del self._files[old_key]
        self._files[new_key] = file_uuid
        self.save()

    def get_file_metadata(self, cdn_file_id=None, local_key=None):
        if local_key is not None and not cdn_file_id:
            cdn_file_id = self.files[local_key]
        return self.client.get_file_metadata(str(cdn_file_id))

    def get_file(self, cdn_file_id: uuid.UUID = None, local_key: int = None, output_dir: Path = None) -> str:
        file_name = self.get_file_metadata(cdn_file_id=cdn_file_id, local_key=local_key).get("file_name")
        if not cdn_file_id:
            cdn_file_id = self._get_cdnfileid_by_local_key(local_key)

        result = self.client.download_file(str(cdn_file_id), output_dir=output_dir, file_name=file_name)
        return result
