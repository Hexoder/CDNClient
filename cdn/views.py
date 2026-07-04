from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import MultipleFileAssociationMixin
from .serializers import AddFileSerializer


class FilesViewSetMixin:

    def _is_multiple(self):
        return issubclass(self.get_serializer_class().Meta.model,
                          MultipleFileAssociationMixin)

    @action(detail=True, methods=['post'])
    def add_file(self, request, *args, **kwargs):
        """Add a file to the associated object."""
        instance = self.get_object()

        serializer = AddFileSerializer(
            data=request.data,
            context={'is_multiple': self._is_multiple()},
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save(instance=instance)
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=['delete'])
    def delete_file(self, request, *args, **kwargs):
        """Delete a file from the associated object."""
        instance = self.get_object()
        local_key = request.query_params.get('local_key', None)
        try:
            if self._is_multiple():
                if not local_key:
                    return Response({"detail": "local_key query param is required for multiple file objects"},
                                    status=status.HTTP_400_BAD_REQUEST)
                instance.remove_file(local_key=local_key)
            else:
                instance.remove_file()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except (KeyError, FileNotFoundError):
            return Response({"error": f"No file '{local_key}' found."},
                            status=status.HTTP_404_NOT_FOUND)
