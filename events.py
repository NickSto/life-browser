from datetime import datetime
import logging
log = logging.getLogger(__name__)


def parse_event(event, book):
  stream = event['stream']
  if stream == 'chat' or stream == 'sms':
    return MessageEvent.from_dict(event, book)
  elif stream == 'call':
    return CallEvent.from_dict(event, book)
  else:
    raise NotImplementedError(f'Cannot parse {stream!r} streams.')


class Event:

  def __init__(self, stream, format, start):
    # The type of event ('sms', 'call', 'chat', 'location', 'photo', etc).
    self.stream = stream
    # The format it originated from ('hangouts', 'voice', 'mytracks', 'geotracker', etc).
    self.format = format
    # Unix timestamp of the event start.
    self.start = start

  def __eq__(self, other):
    if type(self) != type(other):
      return False
    elif self.start != other.start:
      return False
    elif self.stream != other.stream:
      return False
    elif self.format != other.format:
      return False
    else:
      return True


class CommunicationEvent(Event):
  """Abstract parent class for any type of contact from one person to one or several others."""

  def __init__(self, stream, format, start, sender, recipients):
    super().__init__(stream, format, start)
    self.sender = sender
    self.recipients = recipients

  def __eq__(self, other):
    if not super().__eq__(other):
      return False
    #TODO: Is this test appropriate for Contacts? Verify that if the same event is parsed from two
    #      different files, it'll end up with the same Contacts, after deduplication via ContactBook.
    elif self.sender != other.sender:
      return False
    elif sorted(self.recipients) != sorted(other.recipients):
      return False
    else:
      return True

  @staticmethod
  def ids_to_contacts(ids, book):
    return [book.get_by_id(id_) for id_ in ids]


class MessageEvent(CommunicationEvent):
  """Messages like SMS, chats, etc."""

  def __init__(self, stream, format, start, sender, recipients, message, echo=False):
    super().__init__(stream, format, start, sender, recipients)
    self.message = message
    # If this is a message from myself to myself, it will show up twice.
    # `echo` should be True if this is the 2nd appearance of the message.
    self.echo = echo

  @classmethod
  def from_dict(cls, data, book):
    event = cls(
      stream=data['stream'],
      format=data['format'],
      start=data['start'],
      sender=book.get_by_id(data['sender']),
      recipients=cls.ids_to_contacts(data['recipients'], book),
      message=data['message']
    )
    if 'echo' in data:
      event.echo = data['echo']
    return event

  def __str__(self):
    time_str = datetime.fromtimestamp(self.start).strftime('%H:%M:%S')
    if self.stream == 'sms':
      stream_str = ' SMS:'
    else:
      stream_str = ' {}:'.format(self.stream.capitalize())
    recipients_str = ', '.join(map(str, self.recipients[:4]))
    if len(self.recipients) > 4:
      recipients_str += ', and {} others'.format(len(self.recipients)-4)
    return f'{time_str}{stream_str} {self.sender} -> {recipients_str}: {self.message}'

  def __eq__(self, other):
    if not super().__eq__(other):
      return False
    elif self.message != other.message:
      return False
    elif self.echo != other.echo:
      return False
    else:
      return True


class CallEvent(CommunicationEvent):

  """Phone calls, voicemails, video chats, etc."""
  def __init__(self, stream, format, start, end, subtype, sender, recipients):
    super().__init__(stream, format, start, sender, recipients)
    self.end = end
    # subtype examples: "received", "voicemail", "missed"
    self.subtype = subtype

  @property
  def duration(self):
    return self.end-self.start

  def __str__(self):
    if self.subtype == 'missed':
      duration_str = ''
    else:
      duration_str = ' for '+format_time(self.duration)
    recipients_str = ', '.join(map(str, self.recipients[:4]))
    if len(self.recipients) > 4:
      recipients_str += ', and {} others'.format(len(self.recipients)-4)
    return (
      f'{self.start} {self.stream.capitalize()} {self.subtype.lower()}: {self.sender} -> '
      f'{recipients_str}{duration_str}'
    )

  @classmethod
  def from_dict(cls, data, book):
    return cls(
      stream=data['stream'],
      format=data['format'],
      start=data['start'],
      end=data['end'],
      subtype=data['subtype'],
      sender=book.get_by_id(data['sender']),
      recipients=cls.ids_to_contacts(data['recipients'], book),
    )

  def __eq__(self, other):
    if not super().__eq__(other):
      return False
    elif self.end != other.end:
      return False
    elif self.subtype != other.subtype:
      return False
    else:
      return True


class LocationEvent(Event):

  def __init__(self, stream, format, start, nw_lat, nw_lon, accuracy, raw=None):
    super().__init__(stream, format, start, raw=raw)
    self.lat = self.nw_lat = nw_lat
    self.lon = self.nw_lon = nw_lon
    self.accuracy = accuracy

  #TODO: __eq__()


class LocationTrackEvent(Event):

  def __init__(self, stream, format, start, end, nw_lat, nw_lon, se_lat, se_lon, track, raw=None):
    super().__init__(stream, format, start, end=end, raw=raw)
    self.nw_lat = nw_lat
    self.nw_lon = nw_lon
    self.se_lat = se_lat
    self.se_lon = se_lon
    self.track = track

  #TODO: __eq__()


def format_time(total_seconds):
  if total_seconds < 60:
    return str(total_seconds)+' sec'
  elif total_seconds < 60*60:
    seconds = total_seconds % 60
    minutes = total_seconds // 60
    return '{}:{:02d}'.format(minutes, seconds)
  elif total_seconds < 24*60*60:
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return '{}:{:02d}:{:02d}'.format(hours, minutes, seconds)
  else:
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    total_hours = total_minutes // 60
    hours = total_hours % 60
    days = total_hours // 24
    return '{} days {}:{:02d}:{:02d}'.format(days, hours, minutes, seconds)
