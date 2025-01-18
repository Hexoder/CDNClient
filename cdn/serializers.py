from rest_framework import serializers
from .models import File


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = "__all__"


class FileSerializerMixin:

    def get_fields(self):
        # Call the parent method to get the base fields
        fields = super().get_fields()

        # Dynamically add the `files` field
        fields['files'] = FileSerializer(many=True)

        return fields


class AddFileSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(required=True)

    def save(self, instance):
        """
        Save the file for the provided instance.
        """
        uuid = self.validated_data['uuid']

        # Call the instance's `add_file` method
        instance.add_file(uuid=uuid)

        # Optionally, return some response data
        return {"detail": f"File with UUID {uuid} added successfully."}


class DeleteFileSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(required=True)
    hard_delete = serializers.BooleanField(default=False)

    def save(self, instance):
        """
        Save the file for the provided instance.
        """
        uuid = self.validated_data['uuid']
        hard_delete = self.validated_data['hard_delete']

        # Call the instance's `add_file` method
        result = instance.delete_file(uuid=uuid, hard_delete=hard_delete)

        print(result)
        # Optionally, return some response data
        return {"detail": f"File with UUID {uuid} deleted successfully."}
