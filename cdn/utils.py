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
