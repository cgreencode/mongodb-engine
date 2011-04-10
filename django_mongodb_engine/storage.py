import os
import re

import gridfs

from django.conf import settings
from django.core.files.storage import Storage

class GridFSStorage(Storage):
    """
    GridFS Storage Backend for Django.

    This backend aims to add a GridFS storage to upload files to
    using Django file fields.

    The reason why a folders are converted into collections names is to
    improve performance. For example:

    To list a directory '/this/path/' we would have to execute a list
    over the whole collection and then filter the list excluding those not
    starting by '/this/path'. This implementation does something similar but it lists
    the collections and filters the collections names to know what 'directories'
    are contained inside /this/path and then lists the collection to get the files.


    THIS IS UNDER EVALUATION. PLEASE SHARE YOUR COMMENTS AND THOUGHTS.

    TO BE IMPROVED.
    """

    def __init__(self, location='', prefix='storage', sep='/'):
        self.location = os.path.abspath(location)
        self.sep = sep
        self.prefix = prefix

    @property
    def database(self):
        if not hasattr(self, '_database'):
            from django_mongodb_engine.utils import get_default_connection
            self._database = get_default_connection().database
        return self._database

    @property
    def fs(self):
        """
        Gets the GridFS instance and returns it.
        """
        if not hasattr(self, '_fs'):
            self._fs = self._get_gridfs_for_path(self.location)
        return self._fs

    def _get_gridfs_for_path(self, path):
        return gridfs.GridFS(self.database, self._get_collection_name_for(path))

    def _get_collection_name_for(self, path="/"):
        abspath = os.path.abspath(os.path.join(self.location, path))
        collection_name = abspath.replace(os.sep, self.sep)
        if collection_name == self.sep:
            collection_name = ""
        return "%s%s" % (self.prefix, collection_name)

    def _get_abs_path_name_for(self, collection):
        if collection.endswith(".files"):
            collection = collection[:-6]
        path = collection.replace(self.sep, os.sep)[len(self.prefix):]
        return path or "/"

    def _get_rel_path_name_for(self, collection):
        path = self._get_abs_path_name_for(collection)
        return os.path.relpath(os.path.abspath(path), self.location)

    def _get_file(self, path):
        """
        Gets the last version of path.
        """
        try:
            return self.fs.get_last_version(filename=path)
        except gridfs.errors.NoFile:
            return None

    def _open(self, name, mode='rb'):
        """
        Opens a file and returns it.
        """
        if "w" in mode and not self.exists(name):
            return self.fs.new_file(filename=name)

        doc = self._get_file(name)
        if doc:
            return doc
        else:
            raise ValueError("No such file or directory: '%s'" % name)

    def _save(self, name, content):
        self.fs.put(content, filename=name)
        return name

    def delete(self, name):
        """
        Deletes the doc if it exists.
        """
        doc = self._get_file(name)
        if doc:
            self.fs.delete(doc._id)

    def exists(self, name):
        return self.fs.exists(filename=name)

    def listdir(self, path):
        """
        Right now it gets the collections names and filters the list to keep
        just the ones belonging to path and then gets the files inside the fs.

        Needs to be improved
        """
        col_name = self._get_collection_name_for(path)
        path_containing_dirs = re.compile(r"^%s(%s\w+){1}\.files$" % (re.escape(col_name), re.escape(self.sep)))
        collections = filter(path_containing_dirs.match,
                             self.database.collection_names())
        return [self._get_rel_path_name_for(col) for col in collections], self.fs.list()

    def size(self, name):
        doc = self._get_file(name)
        if doc:
            return doc.length
        else:
            raise ValueError("No such file or directory: '%s'" % name)

    def created_time(self, name):
        doc = self._get_file(name)
        if doc:
            return doc.upload_date
        else:
            raise ValueError("No such file or directory: '%s'" % name)
