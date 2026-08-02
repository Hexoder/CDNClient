from email._header_value_parser import ContentType

from channels.db import database_sync_to_async

from cdn.client import CDNClient
from cdn.models import SingleFileAssociationMixin, MultipleFileAssociationMixin

client = CDNClient()


class InfiniteInt:
    def __gt__(self, other):
        return True

    def __ge__(self, other):
        return True

    def __eq__(self, other):
        return False

    def __lt__(self, other):
        return False

    def __le__(self, other):
        return False


class FileMaxedOutError(Exception):

    def __init__(self, max_file_count):
        super().__init__()
        self.max_file_count = max_file_count

    def __str__(self):
        return f"file length maxed out reached, allowed file count: {self.max_file_count}"


@database_sync_to_async
def remove_usages(usages):
    for usage in usages:
        content_type_id = int(usage["content_type_id"])
        object_id = int(usage["object_id"])
        file_id = usage["file_id"]
        local_key = usage["local_key"]

        # Remove From Cache
        cache_key = client._make_key(file_id)
        client._cdn_cache.delete(cache_key)

        try:

            # Get Content Object
            obj = ContentType.objects.get_for_id(content_type_id).get_object_for_this_type(
                pk=object_id)

            # Check if multiple or single, delete uuid from field
            if isinstance(obj, SingleFileAssociationMixin) and obj.file == file_id:
                obj.file = None
            elif isinstance(obj, MultipleFileAssociationMixin) and obj._files.get(local_key, None) == file_id:
                del obj._files[local_key]

            # Direct remove file usage from cdn server
            client.clear_file_usage(file_id=file_id, content_type_id=content_type_id, object_id=object_id,
                                    local_key=local_key)

            # Save Object without synchronize
            obj.save(skip_sync=True)
        except Exception as err:
            print(f"Skipped for {content_type_id}-{object_id}: {file_id}: {err}")
    return True
