#!/usr/bin/env python3
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
from __future__ import unicode_literals
import os
import sys
import json
import time
import errno
import logging
import pathlib
import zipfile
import tarfile
import argparse
import html5lib
from datetime import datetime
try:
  from drivers.voice.gvoiceParser import gvParserLib
except ImportError:
  from gvoiceParser import gvParserLib
try:
  from contacts import Contact, ContactBook
except ImportError:
  root = pathlib.Path(__file__).resolve().parent.parent.parent
  sys.path.insert(0, str(root))
  from contacts import Contact, ContactBook
from lifeapp.models import CallEvent, MessageEvent
from drivers.utils import extract_data


##### Driver interface #####


class VoiceMessageEvent(MessageEvent):
  pass


class VoiceCallEvent(CallEvent):
  pass


def get_events(path, book=None, **kwargs):
  # Implement the driver interface.
  if book is None:
    book = ContactBook()
  archive = Archive(path)
  mynumbers = archive.mynumbers
  me = Contact(is_me=True, name='Me')
  if book.me:
    me = book.me
    mynumbers.extend(me['phones'].keys())
  else:
    book.me = me
  if not mynumbers:
    logging.warning(
      'No numbers of yours provided. May have problems identifying you in conversations.'
    )
  emitted_contacts = set()
  last_event = None
  for raw_record in archive:
    tree = html5lib.parse(raw_record.contents)
    convo = gvParserLib.Parser.process_tree(tree, raw_record.filename, mynumbers)
    subtype = getattr(convo, 'calltype', None) or getattr(convo, 'audiotype', None)
    if subtype is None:
      # It's a Text conversation.
      for message in convo:
        event = get_base_dict(message)
        # event = VoiceMessageEvent(
        sender = convert_contact(message.contact, book)
        recipients = [convert_contact(c, book) for c in message.recipients]
        event['stream'] = 'sms'
        event['message'] = message.text
        event['echo'] = is_echo(event, last_event, sender, recipients)
    else:
      # It's a call.
      if subtype in ('placed', 'received', 'missed'):
        # It's a CallRecord of a Placed, Received, or Missed call.
        event = get_base_dict(convo)
        if convo.calltype == 'placed':
          sender = me
          recipients = [convert_contact(convo.contact, book)]
        else:
          sender = convert_contact(convo.contact, book)
          recipients = [me]
        # event = VoiceCallEvent(
        event['stream'] = 'call'
        event['subtype'] = subtype
      else:
        # It's an AudioRecord of a Voicemail or Recorded call.
        # Well, actually sometimes Voicemails are CallRecords, somehow. So they won't have a filename.
        # See the example of Google Voice - Voicemail - 2009-07-18T23_26_16Z.html
        #TODO: Use the `filename` attribute to find the mp3 of the audio
        #      (Note: it only gives the filename, not the full path).
        event = get_base_dict(convo)
        # event = VoiceCallEvent(
        event['stream'] = 'call'
        event['subtype'] = subtype
        sender = convert_contact(convo.contact, book)
        recipients = [me]
      event['echo'] = is_echo(event, last_event, sender, recipients)
    for contact in [sender]+recipients:
      if contact.id not in emitted_contacts:
        yield contact.to_dict(stream='contact', format='hangouts')
        emitted_contacts.add(contact.id)
    event['sender'] = sender.id
    event['recipients'] = [recip.id for recip in recipients]
    yield event
    last_event = event
    if book and book.me:
      me = book.me


def get_base_dict(voice_record):
  """Get the common set of constructor arguments for Voice Events."""
  data = {
    'format': 'voice',
    #TODO: Check timezone awareness.
    'start': int(time.mktime(voice_record.date.timetuple())),
  }
  if hasattr(voice_record, 'duration'):
    if voice_record.duration is None:
      data['end'] = data['start']
    else:
      data['end'] = int(time.mktime((voice_record.date+voice_record.duration).timetuple()))
  return data


def is_echo(event, last_event, sender, recipients):
  # Is this the 2nd appearance of a text or call from myself to myself?
  if event == last_event:
    if sender.is_me and any([recipient.is_me for recipient in recipients]):
      return True
  return False


def convert_contact(voice_contact, book=None):
  #TODO: I think we're often getting phone numbers in the name field.
  #TODO: We're still ending up with duplicate contacts. When I include the 2018-06-06 Google
  #      Contacts export, plus all Hangouts and Voice exports (Hangouts: 2x 2018-01-30,
  #      Voice: 2018-01-31 and 2015-09-05), I end up with 2 contacts for Amanda: one with her full
  #      name and her phone number with the country code with and without the plus, the other with
  #      just her first name and her number with the country code but no plus.
  name = voice_contact.name
  phone = Contact.normalize_phone(voice_contact.phonenumber)
  if book is None:
    return Contact(is_me=voice_contact.is_me, name=name, phone=phone)
  # Check if the contact already exists.
  # It's not me. Look up existing contacts by name and phone number.
  # First, if it's "me", and there's already a "me", use that.
  me_result = None
  if voice_contact.is_me and book.me:
    me_result = book.me
    if name != 'Me' and not book.me.name:
      book.me.name = name
    if phone not in book.me['phones']:
      book.me['phones'].add(phone)
  # Then, look it up by name:
  name_results = book.get_all('names', name)
  for result in name_results:
    # If we found results, add the phone number.
    if phone and phone not in result['phones']:
      result['phones'].add(phone)
  # Then the phone number:
  phone_results = book.get_all('phones', phone)
  for result in phone_results:
    # If we found results, add the name.
    if name and not result.name:
      result.name = name
  # Return the first name result, first phone result, or if no hits, make and add a new Contact.
  if me_result:
    contact = me_result
  elif name_results:
    contact = name_results[0]
  elif phone_results:
    contact = phone_results[0]
  else:
    contact = Contact(is_me=voice_contact.is_me, name=name, phone=phone)
  if contact.is_me:
    book.me = contact
  book.add(contact)
  return contact


##### Stand-alone part #####

class Archive(object):
  #TODO: Allow reading compressed archives when the top-level filename isn't "Takeout"?
  #      For example, I had one zip file where the root has been renamed from "Takeout" to
  #      "username@gmail.com-20140113T022301Z-Voice".

  def __init__(self, archive_path, phones_path=None, encoding='iso-8859-15'):
    self.path = archive_path
    self.encoding = encoding
    self.phones_path = phones_path
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
      self.phones_path = self.phones_path or os.path.join(self.root, 'Phones.vcf')
    elif self.type in ('zip', 'tar'):
      if self.type == 'zip':
        self.archive_handle = zipfile.ZipFile(self.path)
        self.files = self.archive_handle.namelist()
      elif self.type == 'tar':
        self.archive_handle = tarfile.open(self.path)
        self.files = self.archive_handle.getnames()
      if self.phones_path is None:
        for path in self.files:
          if path.endswith('Phones.vcf'):
            self.phones_path = path

  def __iter__(self):
    if self.type == 'dir':
      for filename in self.files:
        if not filename.endswith('.html'):
          continue
        raw_record = RawRecord(filename=filename)
        path = os.path.join(self.root, 'Calls', filename)
        with open(path, encoding=self.encoding) as filehandle:
          raw_record.contents = filehandle.read()
        yield raw_record
    else:
      for path in self.files:
        if path.startswith('Takeout/Voice/Calls') and path.endswith('.html'):
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
      if not self.phones_path or (self.type == 'dir' and not os.path.isfile(self.phones_path)):
        logging.warning('Could not find a Phones.vcf.')
        self._mynumbers = []
      elif self.type == 'dir':
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


def parse_filename(path):
  filename = os.path.basename(path)
  base, ext = os.path.splitext(filename)
  if ext != '.html':
    logging.warning('Unexpected filename extension {!r}: {!r}'.format(ext, filename))
    return None, None, None
  fields = base.split(' - ')
  if len(fields) <= 1:
    logging.warning('Unexpected filename (too few field): {!r}'.format(filename))
    return None, None, None
  timestamp_str = fields[-1]
  # It's possible for the contact name to contain a ' - '.
  # It's also possible to be missing the middle field (Text, Placed, Received, etc).
  # Handling both requires checking the content of the fields.
  # Note: All 2-field files I've seen are actually Placed or Received.
  if fields[len(fields)-2] in ('Text', 'Placed', 'Received', 'Voicemail', 'Missed', 'Recorded'):
    event_type = fields[len(fields)-2]
    nfields = 3
  else:
    event_type = None
    nfields = 2
  contact_name = ' - '.join(fields[:len(fields)-nfields+1])
  return contact_name, event_type, timestamp_str


DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('record', metavar='record.html',
    help='')
  parser.add_argument('-j', '--json', action='store_true')
  parser.add_argument('-m', '--mynumbers',
    help='Comma-delimited.')
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

  if args.json:
    for event in get_events(args.record):
      print(json.dumps(event))
    return

  if args.mynumbers is None:
    mynumbers = []
  else:
    mynumbers = args.mynumbers.split(',')

  with open(args.record, encoding='iso-8859-15') as record_file:
    tree = html5lib.parse(record_file.read())
    convo = gvParserLib.Parser.process_tree(tree, args.record, mynumbers)

  print('Conversation contact: {} ({})'.format(convo.contact.name, convo.contact.phonenumber))
  for message in convo:
    recipients = ['{} ({})'.format(c.name, c.phonenumber) for c in message.recipients]
    print('{} {} ({}) => {}:\n\t{}'.format(
      message.date,
      message.contact.name,
      message.contact.phonenumber,
      ', '.join(recipients),
      message.text
    ))


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
