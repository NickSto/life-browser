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
import argparse
from datetime import datetime
try:
  from drivers.voice.gvoiceParser import gvParserLib
except ImportError:
  from gvoiceParser import gvParserLib


def get_events(paths):
  # Implement the driver interface.
  for path in paths:
    phones_path = os.path.join(path, 'Phones.vcf')
    if not os.path.isfile(phones_path):
      continue
    mynumbers = get_mynumbers(phones_path)
    calls_path = os.path.join(path, 'Calls')
    for filename in os.listdir(calls_path):
      if 'Text' not in filename:
        #TODO: Real check for what type of event it is.
        continue
      convo_path = os.path.join(calls_path, filename)
      convo = gvParserLib.Parser.process_file(convo_path, mynumbers)
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


def get_mynumbers(phones_path):
  #TODO: Replace with real .vcf parser.
  mynumbers = []
  with open(phones_path) as phones_file:
    for line in phones_file:
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


def get_contact_string(contact):
  if contact.name is None:
    return contact.phonenumber
  elif contact.name == '###ME###':
    return 'Me'
  else:
    return contact.name


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
