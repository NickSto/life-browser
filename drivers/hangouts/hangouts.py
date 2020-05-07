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
import json
import time
import logging
import pathlib
import argparse
from datetime import datetime
try:
  from contacts import Contact, ContactBook
except ImportError:
  root = pathlib.Path(__file__).resolve().parent.parent.parent
  sys.path.insert(0, str(root))
  from contacts import Contact, ContactBook
from drivers.utils import extract_data

#TODO: Deal with participants leaving and joining hangouts chats.
#      Membership can vary over time, but I think this is currently getting the static list of
#      participants Hangouts gives in the metadata for each conversation. I think this really only
#      comes up in actual group chats like the slurm group and the HacDC conversation.

VERSION = '0.2.2'


def get_events(convos):
  # Implement the driver interface.
  # This yields Python dicts, not JSON strings, so the caller has to do the json.dumps().
  book = ContactBook()
  book.indexable.add('gaia_ids')
  emitted_contacts = set()
  for convo in convos:
    for event in convo.events:
      recipients = []
      for participant in convo.participants:
        if participant.id != event.sender_id:
          recipient = participant_to_contact(participant, book)
          if recipient:
            recipients.append(recipient)
      sender_participant = convo.participants.get_by_id(event.sender_id)
      sender = participant_to_contact(sender_participant, book)
      event = {
        'stream': event.type,
        'format': 'hangouts',
        'start': event.timestamp,
        'sender':sender.id,
        'recipients':[recip.id for recip in recipients],
        'message':event.get_formatted_message(),
      }
      #TODO: Yield contacts when they're updated with new info, too.
      contacts_to_emit = [sender]+recipients
      for contact in contacts_to_emit:
        if contact.id not in emitted_contacts:
          yield contact.to_dict(stream='contact', format='hangouts')
          emitted_contacts.add(contact.id)
      yield event


def participant_to_contact(participant, book):
  if participant is None:
    raise ValueError(f'No participant!')
  name = participant.name
  phone = Contact.normalize_phone(participant.phone)
  gaia_id = participant.gaia_id
  # Check if the contact already exists.
  # First, try looking it up by name:
  name_results = book.get_all('names', name)
  for result in name_results:
    # If we found results, add the phone number and gaia_id.
    if phone and phone not in result['phones']:
      result['phones'].add(phone)
    if gaia_id and gaia_id not in result['gaia_ids']:
      result['gaia_ids'].add(gaia_id)
  # Then try looking up by phone number:
  phone_results = book.get_all('phones', phone)
  for result in phone_results:
    # If we found results, add the name and gaia_id.
    if name and not result.name:
      result.name = name
    if gaia_id and gaia_id not in result['gaia_ids']:
      result['gaia_ids'].add(gaia_id)
  # Finally, try looking up by gaia_id:
  gaia_results = book.get_all('gaia_ids', gaia_id)
  for result in gaia_results:
    # If we found results, add the name and phone number.
    if name and not result.name:
      result.name = name
    if phone and phone not in result['phones']:
      result['phones'].add(phone)
  # Return the first name result, first gaia result, first phone result, or if no hits,
  # make and add a new Contact.
  if name_results:
    return name_results[0]
  elif gaia_results:
    return gaia_results[0]
  elif phone_results:
    return phone_results[0]
  else:
    contact = Contact(name=name, phone=phone, gaia_id=gaia_id)
    book.add(contact)
    return contact


##### Parsing code #####


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


class Attachment(object):

  def __init__(self, type, image=None, video=None, audio=None):
    self.type = type
    self.image = image # url
    self.video = video # url
    self.audio = audio # url


class Event(object):

  def __init__(self, id, sender_id, timestamp, message, links=(), attachments=(), type=None):
    self.id = id
    self.sender_id = sender_id
    self.timestamp = timestamp
    self.message = message  # a list
    # Urls detected in the message text.
    self.links = links
    # Images or other media sent as the message. These are their urls.
    self.attachments = attachments
    self.type = type

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

  def print_convo(self, start=0, end=9999999999):
    """Prints conversations in human readable format.
    @return None"""
    for event in self.events:
      if not (start <= event.timestamp <= end):
        continue
      author = self.participants.get_by_id(event.sender_id)
      time_str = datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d %H:%M:%S')
      print('{timestamp}: <{author}> {message}'.format(
          timestamp=time_str,
          author=author,
          message=event.get_formatted_message(),
        )
      )


def read_hangouts(json_data, convo_id=None):
  """Parses the json file.
  A generator that yields conversations."""
  logging.info("Analyzing json file ...")
  if "conversation_state" in json_data:
    jconvos = json_data["conversation_state"]
  else:
    jconvos = json_data["conversations"]
  for meta_convo in jconvos:
    if "conversation_state" in meta_convo:
      jconvo = meta_convo["conversation_state"]
      jevents = meta_convo["conversation_state"]["event"]
    else:
      jconvo = meta_convo["conversation"]
      jevents = meta_convo["events"]
    convo = _extract_convo_data(jconvo, jevents)
    if convo_id is None or convo.id == convo_id:
      yield convo


def _extract_convo_data(convo, events):
  """Extracts the data that belongs to a single conversation.
  @return Conversation object"""
  try:
    # note the initial timestamp of this conversation
    convo_id = convo["conversation_id"]["id"]

    # Find out the participants.
    # Note: It seems sometimes not everyone is included. I've seen situations where the sender of
    # a message isn't listed in the participant_data for the same conversation.
    participant_list = ParticipantList()
    for participant in convo["conversation"]["participant_data"]:
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
    for event in events:
      event_id = event["event_id"]
      sender_id = event["sender_id"]  # has dict values "gaia_id" and "chat_id"
      # Process the timestamp.
      try:
        # The timestamps are in microseconds(!). Convert to seconds.
        timestamp = float(event["timestamp"])/1000000
      except ValueError:
        logging.error('Invalid timestamp "{}"'.format(timestamp))
        timestamp = None
      if start_time is None or timestamp < start_time:
        start_time = timestamp
      if end_time is None or timestamp > end_time:
        end_time = timestamp
      # Is this an SMS or Hangout chat message?
      try:
        if event["delivery_medium"]["medium_type"] == "BABEL_MEDIUM":
          event_type = 'chat'
        else:
          event_type = 'sms'
      except KeyError:
        event_type = None
      #TODO: Deal with HANGOUT_EVENT and VOICEMAIL.
      text = []
      links = []
      attachments = []
      try:
        message_content = event["chat_message"]["message_content"]
        try:
          for segment in message_content["segment"]:
            if segment["type"] == "LINE_BREAK":
              text.append('\n')
            elif segment["type"] == "TEXT":
              text.append(segment["text"])
            elif segment["type"] == "LINK":
              # Store in the "links" list.
              # "LINK" segments also have a "link_data" dict that may contain "link_target" and/or
              # "display_url". The "link_target" seems to always be a google.com url that redirects
              # to the actual link (unless it's an email address, in which case it's a mailto:).
              # When present the "display_url" seems to always be the same as the "text".
              text.append(segment["text"])
              links.append(segment["text"])
        except KeyError:
          pass  # may happen when there is no segment
        try:
          for attachment in message_content["attachment"]:
            # Note: This does not currently catch all attachments. It only gets Google photos
            # and videos (and even then, it doesn't get a url you can download the video from).
            if attachment["embed_item"]["type"][0].upper() == "PLUS_PHOTO":
              if "embeds.PlusPhoto.plus_photo" in attachment["embed_item"]:
                media = attachment["embed_item"]["embeds.PlusPhoto.plus_photo"]
              else:
                media = attachment["embed_item"]["plus_photo"]
              if media['media_type'] == 'VIDEO':
                # Video urls seem to lead to a series of redirects that won't work if you're not
                # logged into Google.
                attachments.append(Attachment('video', image=media['url'], video=media['thumbnail']['url']))
                media_url = media['thumbnail']['url']
              else:
                attachments.append(Attachment('image', image=media['url']))
                media_url = media['url']
              text.append(media_url)
        except KeyError:
          pass  # may happen when there is no (compatible) attachment
      except KeyError:
        continue  # that's okay
      sender_gaia = sender_id['gaia_id']
      if not participant_list.get_by_id(sender_gaia):
        participant_list.add(Participant(sender_gaia, None, None, None))
      event_obj = Event(
        event_id, sender_gaia, timestamp, text, links=links, attachments=attachments, type=event_type
      )
      event_list.add(event_obj)
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


def make_argparser():
  parser = argparse.ArgumentParser(description='Commandline python script that allows reading '
                                               'Google Hangouts logfiles.')
  parser.add_argument('logfile',
    help='filename of the Hangouts log file. Can be a raw or gzipped .json file, or a zip/tarball '
         'exported by Google.')
  parser.add_argument('-j', '--json', dest='format', default='human', const='json',
    action='store_const',
    help='Print the output in the Driver API JSON format.')
  parser.add_argument('-J', '--json-array', action='store_true',
    help='When using --json, add commas and brackets to make the entire output a JSON array.')
  parser.add_argument('-S', '--no-sort', dest='sort', action='store_false', default=True)
  parser.add_argument('-l', '--list', action='store_true',
    help='Just print the list of conversations, not their full contents. Prints one line per '
         'conversation: the start time, the id, and the list of participants.')
  parser.add_argument('-c', '--convo-id',
    help='Show the conversation with given id')
  parser.add_argument('-s', '--start', default=0,
    help='Only show messages from after this timestamp or date ("YYYY-MM-DD" or '
         '"YYYY-MM-DD HH:MM:DD"). If the date doesn\'t include a time, it\'s assumed to be the '
         'start of that day.')
  parser.add_argument('-e', '--end', default=9999999999,
    help='Only show messages from before this timestamp or date (see --start for format).')
  parser.add_argument('-p', '--person',
    help='Only show conversations involving this person. This can be a fuzzy match. If any part of '
         'a participant\'s name matches this (case-insensitive), it\'s considered a hit.')
  parser.add_argument('--exact-person', action='store_true',
    help='Make --person require an exact match. It\'s still case-insensitive.')
  parser.add_argument('-L', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  parser.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  parser.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  parser.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  parser.add_argument('--version', action='version', version=VERSION)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  try:
    start = int(args.start)
  except ValueError:
    start = human_time_to_timestamp(args.start)
  try:
    end = int(args.end)
  except ValueError:
    end = human_time_to_timestamp(args.end)

  validate_file(args.logfile)

  json_data = extract_data(args.logfile, 'Takeout/Hangouts/Hangouts.json', transform='json')
  if json_data is None:
    return 1

  if args.format == 'json':
    if args.json_array:
      print('[')
    first = True
    for obj in get_events(read_hangouts(json_data)):
      if first:
        first = False
      elif args.json_array:
        print(',', end='')
      print(json.dumps(obj))
    if args.json_array:
      print(']')
    return

  all_convos = read_hangouts(json_data, convo_id=args.convo_id)
  if args.sort:
    all_convos = sorted(all_convos, key=lambda c: c.start_time)

  for convo in all_convos:
    if convo.start_time > end or convo.end_time < start:
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
      time_str = datetime.fromtimestamp(convo.start_time).strftime('%Y-%m-%d %H:%M:%S')
      print('{timestamp} {convo_id} {participants}'.format(
          timestamp=time_str,
          convo_id=convo.id,
          participants=convo.participants
        )
      )
    else:
      convo.print_convo(start=start, end=end)


def human_time_to_timestamp(human_time):
  try:
    dt = datetime.strptime(human_time, '%Y-%m-%d %H:%M:%S')
  except ValueError:
    dt = datetime.strptime(human_time + ' 00:00:00', '%Y-%m-%d %H:%M:%S')
  return int(time.mktime(dt.timetuple()))


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error: {}'.format(message))


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
