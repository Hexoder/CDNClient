from rest_framework import serializers

from .client import CDNClient
from .models import SingleFileAssociationMixin, MultipleFileAssociationMixin

client = CDNClient()


class FileSerializerMixin:

    def get_fields(self):
        fields = super().get_fields()
        model = getattr(self.Meta, 'model', None)

        if not model:
            return fields

        if issubclass(model, SingleFileAssociationMixin):
            custom_field_name = getattr(self.Meta, 'file_field_name', None)
            self._real_file_field = "file"
            self._is_multiple = False
            field_name = custom_field_name or "file"
            fields[field_name] = serializers.SerializerMethodField()
            fields['file_id'] = serializers.UUIDField(write_only=True, required=False, allow_null=True, source="file")

        elif issubclass(model, MultipleFileAssociationMixin):
            custom_field_name = getattr(self.Meta, 'files_field_name', None)
            self._real_file_field = "files_local_ids"
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
                    return self._serialize_multiple_files(value)
                else:
                    return self._serialize_single_file(value)

            return dynamic_getter

        raise AttributeError(f"{self.__class__.__name__} object has no attribute {name}")

    def _serialize_single_file(self, file_uuid):
        if not file_uuid:
            return None
        try:
            return client.get_file_metadata(str(file_uuid))
        except Exception:
            return None

    def _serialize_multiple_files(self, file_id_uuid_dict: dict):

        # TODO; change results to dictionary and store file_local_ids as it's key

        if not file_id_uuid_dict:
            return {}
        results = []  # TODO; change to => results = {}
        for local_id, uuid in file_id_uuid_dict.items():
            try:
                metadata = client.get_file_metadata(str(uuid))
                if metadata:
                    results.append({str(local_id): metadata})
                    # TODO: change to => results.update({str(local_id): metadata})
            except Exception as err:
                print(err)
        return results


class AddFileSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(required=True)

    def save(self, instance):
        """
        Save the file for the provided instance.
        """
        uuid = self.validated_data['uuid']

        # Call the instance's `add_file` method
        try:
            instance.add_file(cdn_file_uuid=str(uuid))
            # Optionally, return some response data
            return {"detail": f"File with UUID {uuid} added successfully."}
        except Exception as err:
            return {"error": str(err)}
