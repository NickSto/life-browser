#!/usr/bin/env python
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
import os
import sys
import time
import errno
import logging
import zipfile
import tarfile
import argparse
import html5lib
from datetime import datetime
try:
  from drivers.voice.gvoiceParser import gvParserLib
except ImportError:
  from gvoiceParser import gvParserLib


def get_events(paths, mynumbers=None):
  # Implement the driver interface.
  for path in paths:
    archive = Archive(path)
    if mynumbers is not None:
      archive.mynumbers.extend(mynumbers)
    if not archive.mynumbers:
      raise ValueError('No numbers found in Phones.vcf. Please provide manually.')
    for raw_record in archive:
      if 'Text' not in raw_record.filename:
        #TODO: Real check for what type of event it is.
        continue
      tree = html5lib.parse(raw_record.contents)
      convo = gvParserLib.Parser.process_tree(tree, raw_record.filename, archive.mynumbers)
      # Figure out who are the two people in the conversation.
      #TODO: Group texts.
      contact1 = convo.contact
      for message in convo:
        if message.receiver != contact1:
          contact2 = message.receiver
          break
      for message in convo:
        if message.receiver == contact1:
          receiver = contact1
          sender = contact2
        else:
          receiver = contact2
          sender = contact1
        yield {
          'type': 'voice',
          #TODO: Check timezone awareness.
          'timestamp': int(time.mktime(message.date.timetuple())),
          'subtype': 'sms',
          'sender': get_contact_string(sender),
          'recipients': (get_contact_string(receiver),),
          'message': message.text,
          'raw': {
            'conversation': convo,
            'event': message,
            'sender': sender,
            'receiver': receiver,
          }
        }


def get_contact_string(contact):
  if contact.name is None:
    return contact.phonenumber
  elif contact.name == '###ME###':
    return 'Me'
  else:
    return contact.name


class Archive(object):

  def __init__(self, archive_path, encoding='iso-8859-15'):
    self.path = archive_path
    self.encoding = encoding
    self._mynumbers = None
    # Determine the type archive we were given.
    if os.path.isdir(self.path):
      self.type = 'dir'
    elif os.path.isfile(self.path):
      if self.path.endswith('.zip'):
        self.type = 'zip'
      elif (self.path.endswith('.tar.gz') or self.path.endswith('.tar.bz')
            or self.path.endswith('.tar.xz') or self.path.endswith('.tgz')
            or self.path.endswith('.tbz') or self.path.endswith('.txz')):
        self.type = 'tar'
      else:
        raise ValueError('The provided file isn\'t of a known type: "{}".'.format(self.path))
    else:
        raise ValueError('The provided path wasn\'t recognized: "{}".'.format(self.path))
    self._get_files()

  def _get_files(self):
    # Get the list of files.
    if self.type == 'dir':
      if os.path.isdir(os.path.join(self.path, 'Voice')):
        self.root = os.path.join(self.path, 'Voice')
      elif os.path.isdir(os.path.join(self.path, 'Calls')):
        self.root = self.path
      else:
        raise ValueError('The provided directory doesn\'t seem to contain a valid Google Voice '
                         'archive: "{}".'.format(self.path))
      self.files = os.listdir(os.path.join(self.root, 'Calls'))
      self.phones_path = os.path.join(self.root, 'Phones.vcf')
    elif self.type == 'zip':
      self.archive_handle = zipfile.ZipFile(self.path)
      self.files = self.archive_handle.namelist()
      for path in self.files:
        if path.endswith('Phones.vcf'):
          self.phones_path = path
    elif self.type == 'tar':
      self.archive_handle = tarfile.open(self.path)
      self.files = self.archive_handle.getnames()
      for path in self.files:
        if path.endswith('Phones.vcf'):
          self.phones_path = path

  def __iter__(self):
    if self.type == 'dir':
      for filename in self.files:
        raw_record = RawRecord(filename=filename)
        path = os.path.join(self.root, 'Calls', filename)
        with open(path, encoding=self.encoding) as filehandle:
          raw_record.contents = filehandle.read()
        yield raw_record
    else:
      for path in self.files:
        if path.startswith('Takeout/Voice/Calls'):
          raw_record = RawRecord(filename=os.path.basename(path))
          if self.type == 'zip':
            raw_record.contents = str(self.archive_handle.read(path), self.encoding)
          elif self.type == 'tar':
            filehandle = self.archive_handle.extractfile(path)
            raw_record.contents = str(filehandle.read(), self.encoding)
          yield raw_record

  @property
  def mynumbers(self):
    if self._mynumbers is None:
      if self.type == 'dir':
        with open(self.phones_path) as phones_file:
          self._mynumbers = self.get_mynumbers(phones_file)
      elif self.type == 'zip':
        phones_str = str(self.archive_handle.read(self.phones_path), 'utf8')
        self._mynumbers = self.get_mynumbers(phones_str)
      elif self.type == 'tar':
        phones_file = self.archive_handle.extractfile(self.phones_path)
        phones_str = str(phones_file.read(), 'utf8')
        self._mynumbers = self.get_mynumbers(phones_str)
    return self._mynumbers

  @classmethod
  def get_mynumbers(cls, phones_data):
    #TODO: Replace with real .vcf parser.
    mynumbers = []
    if hasattr(phones_data, 'splitlines'):
      phones_lines = phones_data.splitlines()
    else:
      phones_lines = phones_data
    for line in phones_lines:
      try:
        key, value = line.rstrip('\r\n').split(':')
      except ValueError:
        continue
      if key.startswith('item') and key.endswith('.TEL'):
        try:
          int(key[4:-4])
        except ValueError:
          continue
        mynumbers.append(value.lstrip('+'))
      elif key.startswith('TEL;TYPE='):
        mynumbers.append(value.lstrip('+'))
    return mynumbers


class RawRecord(object):
  def __init__(self, filename=None, contents=None):
    self.filename = filename
    self.contents = contents


DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('record', metavar='record.html',
    help='')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  parser.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  parser.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  parser.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')
  tone_down_logger()

  for message in gvParserLib.Parser.process_file(args.record, {}):
    print(message)


def tone_down_logger():
  """Change the logging level names from all-caps to capitalized lowercase.
  E.g. "WARNING" -> "Warning" (turn down the volume a bit in your log files)"""
  for level in (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG):
    level_name = logging.getLevelName(level)
    logging.addLevelName(level, level_name.capitalize())


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except IOError as ioe:
    if ioe.errno != errno.EPIPE:
      raise
