#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The article included in this repository is licensed under a Attribution-NonCommercial-ShareAlike 3.0
license, meaning that you are free to copy, distribute, transmit and adapt this work for non-
commercial use, but that you must credit Fabian Mueller as the original author of the piece, and
provide a link to the source: https://bitbucket.org/dotcs/hangouts-log-reader/

You can read the full license here:
http://creativecommons.org/licenses/by-nc-sa/3.0/us/
"""

import os
import sys
import time
import json
import gzip
import zipfile
import tarfile
import logging
import argparse

from datetime import datetime

VERSION = "0.2"


class Participant(object):

  def __init__(self, gaia_id, chat_id, name, phone):
    self.name = name
    self.phone = phone
    self.gaia_id = gaia_id
    self.chat_id = chat_id

  @property
  def id(self):
    return self.gaia_id

  @id.setter
  def id(self, value):
    self.gaia_id = value

  def __str__(self):
    """@return name of the participant or its id if name is None"""
    if self.name is None:
      if self.phone is None:
        return self.id
      else:
        return self.phone
    else:
      return self.name


class ParticipantList(object):

  def __init__(self):
    self.p_list = {}
    self.current_iter = 0
    self.max_iter = 0

  def add(self, participant):
    """Adds a participant to the list.
    @return the participant list"""
    self.p_list[participant.id] = participant
    return self.p_list

  def get_by_id(self, id):
    """Queries a participant by its id.
    @return the participant or None if id is not listed"""
    try:
      return self.p_list[id]
    except:
      return None

  def __iter__(self):
    self.current_iter = 0
    self.max_iter = len(self.p_list)-1
    return self

  def __next__(self):
    if self.current_iter > self.max_iter:
      raise StopIteration
    else:
      self.current_iter += 1
      return list(self.p_list.values())[self.current_iter-1]

  def __str__(self):
    """@return names of the participants seperated by a comma"""
    return ', '.join(map(str, self.p_list.values()))


class Event(object):

  def __init__(self, id, sender_id, timestamp, message):
    self.id = id
    self.sender_id = sender_id
    self.timestamp = timestamp
    self.message = message  # a list

  def get_formatted_message(self):
    """Get a formatted message (the messages are joined by a space).
    @return message (string)"""
    return ' '.join(self.message)


class EventList(object):

  def __init__(self):
    self.event_list = {}
    self.current_iter = 0
    self.max_iter = 0

  def add(self, event):
    """Adds an event to the event list
    @return event list"""
    self.event_list[event.id] = event
    return self.event_list

  def get_by_id(self, id):
    """Get an event by its id.
    @returns event"""
    try:
      return self.event_list[id]
    except:
      return None

  def __iter__(self):
    self.current_iter = 0
    self.max_iter = len(self.event_list)-1
    return self

  def __next__(self):
    if self.current_iter > self.max_iter:
      raise StopIteration
    else:
      self.current_iter += 1
      return list(self.event_list.values())[self.current_iter-1]


class Conversation(object):

  def __init__(self, id, start_time, end_time, participants, events):
    self.id = id
    self.start_time = start_time
    self.end_time = end_time
    self.participants = participants  # a ParticipantsList
    self.events = events
    self._events_sorted = False

  def __str__(self):
    return self.id

  @property
  def events(self):
    """Getter method for the sorted events.
    If the events are not sorted yet (checked via self._events_sorted), it sorts
    them and stores them back in self.events.
    @return events of the conversation, sorted by timestamp"""
    if not self._events_sorted:
      self._events = sorted(self._events, key=lambda event: event.timestamp)
      self._events_sorted = True
    return self._events

  @events.setter
  def events(self, value):
    self._events = value

  def get_events_unsorted(self):
    """Get the list of events, but skip sorting.
    @return events of the conversation (unsorted)"""
    return self.events

  def print_convo(self):
    """Prints conversations in human readable format.
    @return None"""
    participants = self.participants
    for event in self.events:
      author = "<UNKNOWN>"
      author_id = participants.get_by_id(event.sender_id)
      if author_id:
        author = author_id.name
      print("%(timestamp)s: <%(author)s> %(message)s" % \
          {
            "timestamp": datetime.fromtimestamp(float(event.timestamp)/10**6),
            "author": author,
            "message": event.get_formatted_message(),
          })


def read_hangouts(json_data, convo_id=None):
  """Parses the json file.
  Yields the conversation list or a complete conversation depending on the users choice."""
  logging.info("Analyzing json file ...")
  for convo in json_data["conversation_state"]:
    convo = _extract_convo_data(convo)
    if convo_id is None or convo.id == convo_id:
      yield convo


def _extract_convo_data(convo):
  """Extracts the data that belongs to a single conversation.
  @return Conversation object"""
  try:
    # note the initial timestamp of this conversation
    convo_id = convo["conversation_id"]["id"]

    # find out the participants
    participant_list = ParticipantList()
    for participant in convo["conversation_state"]["conversation"]["participant_data"]:
      gaia_id = participant["id"]["gaia_id"]
      chat_id = participant["id"]["chat_id"]
      try:
        name = participant["fallback_name"]
      except KeyError:
        name = None
      try:
        phone = participant["phone_number"]["e164"]
      except KeyError:
        phone = None
      participant_list.add(Participant(gaia_id, chat_id, name, phone))

    event_list = EventList()

    start_time = None
    end_time = None
    for event in convo["conversation_state"]["event"]:
      event_id = event["event_id"]
      sender_id = event["sender_id"]  # has dict values "gaia_id" and "chat_id"
      try:
        timestamp = int(event["timestamp"])
      except ValueError:
        timestamp = event['timestamp']
      if start_time is None:
        start_time = timestamp
      end_time = timestamp
      text = []
      try:
        message_content = event["chat_message"]["message_content"]
        try:
          for segment in message_content["segment"]:
            if segment["type"].lower() in ("TEXT".lower(), "LINK".lower()):
              text.append(segment["text"])
        except KeyError:
          pass  # may happen when there is no (compatible) attachment
        try:
          for attachment in message_content["attachment"]:
            # if there is a Google+ photo attachment we append the URL
            if attachment["embed_item"]["type"][0].lower() == "PLUS_PHOTO".lower():
              text.append(attachment["embed_item"]["embeds.PlusPhoto.plus_photo"]["url"])
        except KeyError:
          pass  # may happen when there is no (compatible) attachment
      except KeyError:
        continue  # that's okay
      # finally add the event to the event list
      event_list.add(Event(event_id, sender_id["gaia_id"], timestamp, text))
  except KeyError:
    raise RuntimeError("The conversation data could not be extracted.")
  return Conversation(convo_id, start_time, end_time, participant_list, event_list)


def validate_file(filename):
  """Checks if a file is valid or not.
  Raises a ValueError if the file could not be found.
  @return filename if everything is fine"""
  if not os.path.isfile(filename):
    raise ValueError("The given file is not valid.")
  return filename


def main(argv):
  parser = argparse.ArgumentParser(description='Commandline python script that allows reading Google Hangouts logfiles. Version: %s' % VERSION)
  parser.set_defaults(start=0, end=9999999999)

  parser.add_argument('logfile', type=str, help='filename of the Hangouts log file. Can be a '
    'raw or gzipped .json file, or a zip/tarball exported by Google.')
  parser.add_argument('--no-sort', '-S', dest='sort', action='store_false', default=True)
  parser.add_argument('--list', '-l', action='store_true', help='Just print the list of '
    'conversations, not their full contents. Prints one line per conversation: the start time, '
    'the id, and the list of participants.')
  parser.add_argument('--convo-id', '-c', type=str, help='shows the conversation with given id')
  parser.add_argument('--start', '-s', help='Only show conversations that began later than this '
    'timestamp or date ("YYYY-MM-DD" or "YYYY-MM-DD HH:MM:DD")')
  parser.add_argument('--end', '-e', help='Only show conversations that ended earlier than this '
    'timestamp or date ("YYYY-MM-DD" or "YYYY-MM-DD HH:MM:DD")')
  parser.add_argument('--person', '-p', help='Only show conversations involving this person. This '
    'can be a fuzzy match. If any part of a participant\'s name matches this (case-insensitive), '
    'it\'s considered a hit.')
  parser.add_argument('--exact-person', action='store_true', help='Make --person require an exact '
    'match.')
  parser.add_argument('--log', '-L', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  parser.add_argument('--quiet', '-q', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  parser.add_argument('--verbose', '-v', dest='volume', action='store_const', const=logging.INFO)
  parser.add_argument('--debug', '-D', dest='volume', action='store_const', const=logging.DEBUG)

  args = parser.parse_args()

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')
  tone_down_logger()

  try:
    start = int(args.start) * 1000000
  except ValueError:
    start = human_time_to_timestamp(args.start) * 1000000
  try:
    end = int(args.end) * 1000000
  except ValueError:
    end = human_time_to_timestamp(args.end) * 1000000

  validate_file(args.logfile)

  json_data = extract_data(args.logfile)

  all_convos = read_hangouts(json_data, convo_id=args.convo_id)
  if args.sort:
    all_convos = sorted(all_convos, key=lambda c: c.start_time)

  for convo in all_convos:
    if convo.start_time < start or convo.end_time > end:
      continue
    if args.convo_id and args.convo_id != convo.id:
      continue
    if args.person:
      hit = False
      for participant in convo.participants:
        if args.exact_person:
          if args.person.lower() == str(participant).lower():
            hit = True
        else:
          if args.person.lower() in str(participant).lower():
            hit = True
      if not hit:
        continue
    if args.list:
      print('{} {} {}'.format(datetime.fromtimestamp(convo.start_time/1000000),
                              convo.id, convo.participants))
    else:
      convo.print_convo()


def human_time_to_timestamp(human_time):
  try:
    dt = datetime.strptime(human_time, '%Y-%m-%d %H:%M:%S')
  except ValueError:
    dt = datetime.strptime(human_time + ' 00:00:00', '%Y-%m-%d %H:%M:%S')
  return int(time.mktime(dt.timetuple()))


def extract_data(path):
  if path.endswith('.json'):
    # The raw json file.
    with open(path) as json_file:
      return json.load(json_file)
  elif path.endswith('.json.gz'):
    # A gzipped json file.
    with gzip.open(path, mode='rt') as gzip_file:
      return json.load(gzip_file)
  elif path.endswith('.zip'):
    # Assume it's a zip file exported from Google.
    with zipfile.ZipFile(path) as zipball:
      for member in zipball.namelist():
        if member == 'Takeout/Hangouts/Hangouts.json':
          json_str = str(zipball.read(member), 'utf8')
          return json.loads(json_str)
  elif (path.endswith('.tar.gz') or path.endswith('.tar.bz') or path.endswith('.tar.xz')
        or path.endswith('.tgz') or path.endswith('.tbz') or path.endswith('.txz')):
    # Assume it's a tarball exported from Google.
    with tarfile.open(path) as tarball:
      for member in tarball.getnames():
        if member == 'Takeout/Hangouts/Hangouts.json':
          json_file = tarball.extractfile(member)
          json_str = str(json_file.read(), 'utf8')
          return json.loads(json_str)
  else:
    fail('File ending of "{}" not recognized.'.format(os.path.basename(path)))


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
  except BrokenPipeError:
    pass
