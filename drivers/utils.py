import gzip
import json
import os
import tarfile
import zipfile


def extract_data(file_path, record_path, format=None, transform=None):
  """Read data from a file, understanding many formats (gzip, tarball, zip, or plaintext).
  Arguments:
    `file_path`:   The path of the data file on disk.
    `record_path`: If the `file_path` is a zip/tar archive, this is the path to the data file within
                   the archive.
    `format`:      Assume the data file is in this format, instead of inferring based on the file
                   extension. Valid formats: 'tar', 'zip', 'gz', 'text'.
    `transform`:   Parse/convert the data into this form. Default is to read the data as text and
                   return a string. If `transform` is `json`, it will be parsed as json and the
                   resulting object will be returned."""
  filehandle = None
  contents = None
  ext = os.path.splitext(file_path)[1]
  # tarball
  if format == 'tar' or (format is None and (ext in ('.tgz', '.tbz', '.txz') or
      file_path.endswith('.tar.gz') or file_path.endswith('.tar.bz') or file_path.endswith('.tar.xz'))):
    with tarfile.open(file_path) as tarball:
      for member in tarball.getnames():
        if member == record_path:
          filehandle = tarball.extractfile(member)
          contents = str(filehandle.read(), 'utf8')
  # zip file
  elif format == 'zip' or (format is None and ext == '.zip'):
    with zipfile.ZipFile(file_path) as zipball:
      for member in zipball.namelist():
        if member == record_path:
          contents = str(zipball.read(member), 'utf8')
  # A gzip file.
  elif format == 'gz' or (format is None and ext == '.gz'):
    filehandle = gzip.open(file_path, mode='rt')
  # A raw text file.
  elif format == 'text' or (format is None and ext in ('.txt', '.json')):
    filehandle = open(file_path)
  else:
    raise ValueError('Format {!r} and file ending of {!r} not recognized.'
                     .format(format, os.path.basename(file_path)))
  # Do whatever reading and transforming is necessary, and return the results.
  if contents is None:
    if transform == 'json':
      contents = json.load(filehandle)
    else:
      contents = filehandle.read()
    if hasattr(filehandle, 'close') and not getattr(filehandle, 'closed', True):
      filehandle.close()
  return contents
