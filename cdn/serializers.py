from rest_framework import serializers

from .client import CDNClient
from .models import SingleFileAssociationMixin, MultipleFileAssociationMixin

client = CDNClient()


class FileSerializerMixin:

    def get_fields(self):
        fields = super().get_fields()
        model = getattr(self.Meta, 'model', None)
        custom_field_name = getattr(self.Meta, 'file_field_name', None)

        if not model:
            return fields

        if issubclass(model, SingleFileAssociationMixin):
            self._real_file_field = "file"
            self._is_multiple = False
            field_name = custom_field_name or "file"
            fields[field_name] = serializers.SerializerMethodField()

        elif issubclass(model, MultipleFileAssociationMixin):
            self._real_file_field = "files"
            self._is_multiple = True
            field_name = custom_field_name or "files"
            fields[field_name] = serializers.SerializerMethodField()

        return fields

    def __getattr__(self, name):
        if name.startswith('get_'):
            requested_field_name = name[4:]  # remove 'get_' prefix
            model = getattr(self.Meta, 'model', None)

            if not model:
                raise AttributeError(f"No model found for {self}")

            # Dynamically generate getter
            def dynamic_getter(obj):
                real_field = getattr(self, '_real_file_field', None)
                is_multiple = getattr(self, '_is_multiple', False)

                if not real_field:
                    return None

                value = getattr(obj, real_field, None)

                if not value:
                    return None

                if is_multiple:
                    return self.serialize_multiple_files(value)
                else:
                    return self.serialize_single_file(value)

            return dynamic_getter

        raise AttributeError(f"{self.__class__.__name__} object has no attribute {name}")

    def serialize_single_file(self, file_uuid):
        if not file_uuid:
            return None
        try:
            return client.get_file_metadata(str(file_uuid))
        except Exception:
            return None

    def serialize_multiple_files(self, file_uuid_list):
        if not file_uuid_list:
            return []
        results = []
        for uuid in file_uuid_list:
            try:
                metadata = client.get_file_metadata(str(uuid))
                if metadata:
                    results.append(metadata)
            except Exception:
                continue
        return results

