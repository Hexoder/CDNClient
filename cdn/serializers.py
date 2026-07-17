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

    def validate(self, attrs):
        instance = self.context["instance"]
        local_key = attrs.get("local_key")
        replace = attrs.get("replace", False)
        cdn_file_uuid = attrs.get('uuid')

        if self.context.get("is_multiple") and not replace:
            if instance.files.get(local_key):
                raise serializers.ValidationError({
                    "local_key": (
                        f"'{local_key}' already has a file. "
                        "Pass replace=true to overwrite."
                    )
                })
            local_key = instance._get_local_key_by_cdn_uuid(str(cdn_file_uuid))
            if local_key:
                raise serializers.ValidationError({
                    "uuid": (
                        f"file with uuid '{cdn_file_uuid}' already assigned to key '{local_key}' "
                        "Pass replace=true to overwrite."
                    )
                })

        return attrs

    def save(self):
        data = self.validated_data
        instance = self.context["instance"]

        if self.context.get("is_multiple"):
            instance.add_file(
                cdn_file_uuid=str(data["uuid"]),
                local_key=data.get("local_key"),
                replace=data.get("replace", False),
            )
        else:
            instance.set_file(cdn_file_uuid=str(data["uuid"]))

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
