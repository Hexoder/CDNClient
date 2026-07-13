from rest_framework import serializers

from .client import CDNClient
from .models import SingleFileAssociationMixin, MultipleFileAssociationMixin
from .utils import FileMaxedOutError

client = CDNClient()


class FileSerializerMixin:

    def get_fields(self):
        fields = super().get_fields()
        model = getattr(self.Meta, 'model', None)
        if not model:
            return fields

        if issubclass(model, SingleFileAssociationMixin):
            field_name = getattr(self.Meta, 'file_field_name', None) or "file"
            self._real_file_field = "file"
            self._is_multiple = False
            fields[field_name] = serializers.SerializerMethodField(
                method_name="get_file_representation"
            )
            fields['file_id'] = serializers.UUIDField(
                write_only=True, required=False, allow_null=True, source="file"
            )

        elif issubclass(model, MultipleFileAssociationMixin):
            field_name = getattr(self.Meta, 'files_field_name', None) or "files"
            self._real_file_field = "files"
            self._is_multiple = True
            fields[field_name] = serializers.SerializerMethodField(
                method_name="get_file_representation"
            )

        return fields

    def get_file_representation(self, obj):
        real_field = getattr(self, '_real_file_field', None)
        if not real_field:
            return None

        value = getattr(obj, real_field, None)
        if not value:
            return None

        if getattr(self, '_is_multiple', False):
            return self._serialize_multiple_files(value)
        return self._serialize_single_file(value)

    def _serialize_single_file(self, file_uuid):
        if not file_uuid:
            return None
        try:
            return client.get_file_metadata(str(file_uuid))
        except Exception:
            return None

    def _serialize_multiple_files(self, file_map: dict):
        if not file_map:
            return {}
        results = []
        for local_key, cdn_uuid in file_map.items():
            try:
                metadata = client.get_file_metadata(str(cdn_uuid))
                if metadata:
                    metadata['local_key'] = str(local_key)
                    results.append(metadata)
            except Exception as err:
                print(err)
        return results


class AddFileSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(required=True)
    local_key = serializers.CharField(required=False)
    replace = serializers.BooleanField(required=False, default=False)

    def save(self, instance):
        data = self.validated_data
        try:
            if self.context.get('is_multiple'):
                instance.add_file(
                    cdn_file_uuid=str(data['uuid']),
                    local_key=data['local_key'],
                    replace=data.get('replace', False),
                )
            else:
                instance.set_file(cdn_file_uuid=str(data['uuid']))
        except FileExistsError:
            raise serializers.ValidationError(
                {"local_key": f"'{data.get('local_key')}' already has a file. "
                              f"Pass replace=true to overwrite."}
            )
        except FileMaxedOutError as err:
            raise serializers.ValidationError({"detail": str(err)})

        return {"detail": f"File {data['uuid']} added successfully."}


class SwapFileSerializer(serializers.Serializer):
    local_key1 = serializers.CharField(required=True)
    local_key2 = serializers.CharField(required=True)

    def save(self, instance):
        data = self.validated_data
        local_key1 = data['local_key1']
        local_key2 = data['local_key2']
        try:
            instance.swap_files(local_key1=local_key1, local_key2=local_key2)

        except Exception as err:
            raise serializers.ValidationError(
                str(err)
            )

        return {"detail": f"File {local_key1} successfully swapped with {local_key2}."}


class ChangeFileKeySerializer(serializers.Serializer):
    old_key = serializers.CharField(required=True)
    new_key = serializers.CharField(required=True)

    def save(self, instance):
        data = self.validated_data
        old_key = data['old_key']
        new_key = data['new_key']
        try:
            instance.change_file_key(old_key=old_key, new_key=new_key)

        except Exception as err:
            raise serializers.ValidationError(
                str(err)
            )
        return {"detail": f"File {old_key} successfully changed to {new_key}."}
