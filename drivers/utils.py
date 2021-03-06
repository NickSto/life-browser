import gzip
import json
import os
import pathlib
import subprocess
import tarfile
import yaml
import zipfile
import events
import contacts


DRIVERS_DIR = pathlib.Path(__file__).parent

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
  else:
    if transform == 'json':
      contents = json.loads(contents)
  return contents


def discover_drivers(drivers_root=DRIVERS_DIR):
  drivers = {}
  for config_path in find_driver_configs(drivers_root):
    with config_path.open('r') as config_file:
      driver = yaml.safe_load(config_file)
    driver['dir'] = config_path.parent
    name = driver['name']
    drivers[name] = driver
  return drivers


def find_driver_configs(drivers_root):
  for dirpath_str, dirname_strs, filename_strs in os.walk(drivers_root):
    for filename_str in filename_strs:
      if filename_str.lower() == 'driver.yaml':
        yield pathlib.Path(dirpath_str, filename_str)


def get_events(driver, path, book):
  """Execute a driver on input data and return `Event`s.
  This will use the `book` argument to harmonize the `Contact`s associated with the `Event`s with
  all the `Contact`s known to this point."""
  # Use list() to force rehydrate_objects() to finish before we start.
  # This will cause all the Contacts to be in their final form - no more modifications.
  for event in list(rehydrate_objects(run_driver(driver, path))):
    event.update_contacts(book)
    yield event


def rehydrate_objects(raw_objects):
  """Transform the raw dicts from a driver into `Event`s and `Contact`s.
  The `Contact` `id`s will only be local `id`s valid for this execution. This will not translate
  them into globally valid `id`s."""
  book = contacts.ContactBook(index_policy='blacklist', unindexable=('notes', 'addresses'))
  for raw_object in raw_objects:
    if raw_object['stream'] == 'contact':
      contact = contacts.Contact.from_dict(raw_object)
      # If the driver finds new info for a previously-seen Contact (like a new phone #), it will
      # yield the same Contact again, with the same id, but with the new info.
      # Update the old version with the new info.
      # Don't just replace it in the book, since the old object will still be referenced by an event.
      existing_contact = book.get_by_id(contact.id)
      if existing_contact:
        existing_contact.merge(contact)
      else:
        book.add(contact)
    else:
      yield events.parse_event(raw_object, book)


def run_driver(driver, path):
  command = get_driver_command(driver, path)
  process = subprocess.Popen(command, stdout=subprocess.PIPE, encoding='utf8')
  for line in process.stdout:
    yield json.loads(line)


def get_driver_command(driver, data_path):
  exe_file = driver['execution']['exe']
  executable = driver['dir'] / exe_file
  args = driver['execution']['args']
  command = [str(executable)] + args
  substituted = False
  for i, arg in enumerate(command):
    if arg is None:
      if substituted:
        raise ValueError(
          f"More than one '~' placeholder encountered in args for {driver['name']} driver."
        )
      command[i] = str(data_path)
      substituted = True
  return command


def parse_event(json_event):
  raise NotImplementedError("Haven't implemented parsing Events.")

