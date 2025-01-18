from rest_framework import status
from rest_framework.response import Response
from rest_framework.generics import CreateAPIView, DestroyAPIView
from .models import File
from rest_framework.decorators import action

from .serializers import AddFileSerializer, DeleteFileSerializer


class FileApiViewMixin:

    @action(detail=True, methods=['post'])
    def add_file(self, request, *args, **kwargs):
        """Add a file to the associated object."""
        instance = self.get_object()
        try:

            # Pass the request data to the serializer
            serializer = AddFileSerializer(data=request.data)
            if serializer.is_valid():
                # Let the serializer handle the logic
                result = serializer.save(instance=instance)
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as err:
            return Response(str(err), status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def delete_file(self, request, *args, **kwargs):
        """Delete a file from the associated object."""
        instance = self.get_object()
        try:
            serializer = DeleteFileSerializer(data=request.data)
            if serializer.is_valid():
                result = serializer.save(instance=instance)

                return Response(result, status=status.HTTP_200_OK)

            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as err:
            return Response({"error": str(err)}, status=status.HTTP_400_BAD_REQUEST)
