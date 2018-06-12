from datetime import datetime

class Event(object):

  def __init__(self, stream, format, start, end=None, raw=None, **optionals):
    # stream: 'sms', 'call', 'chat', 'location', 'photo', etc
    # format: 'hangouts', 'voice', 'mytracks', 'geotracker', etc
    self.stream = stream
    self.format = format
    self.start = start
    self.end = end
    if raw is None:
      self.raw = {}
    else:
      self.raw = raw

  def _generic_eq(self, other):
    if self.start != other.start:
      return False
    if self.stream != other.stream:
      return False
    if self.format != other.format:
      return False
    if self.end != other.end:
      return False
    return True

  def __eq__(self, other):
    if not self._generic_eq(other):
      return False
    if self.raw != other.raw:
      return False
    for attr in dir(self):
      if attr.startswith('_'):
        continue
      if not hasattr(other, attr):
        return False
      if getattr(self, attr) != getattr(other, attr):
        return False
    return True


class MessageEvent(Event):
  """Messages like SMS, chats, etc."""
  def __init__(self, stream, format, start, sender, recipients, message, raw=None):
    super().__init__(stream, format, start, raw=raw)
    self.sender = sender
    self.recipients = recipients
    self.message = message

  #TODO: Overflow for recipients like "a, b, c, and 23 others".
  def __str__(self):
    time_str = datetime.fromtimestamp(self.start).strftime('%H:%M:%S')
    if self.stream == 'sms':
      stream_str = ' SMS:'
    else:
      stream_str = ' {}:'.format(self.stream.capitalize())
    return '{start}{type} {sender} -> {recipients}: {message}'.format(
      start=time_str,
      type=stream_str,
      sender=self.sender,
      recipients=', '.join(map(str, self.recipients)),
      message=self.message
    )

  def __eq__(self, other):
    if not self._generic_eq(other):
      return False
    if self.message != other.message:
      return False
    #TODO: Is this test appropriate for Contacts? Verify that if the same event is parsed from two
    #      different files, it'll end up with the same Contacts, after deduplication via ContactBook.
    if self.sender != other.sender:
      return False
    if sorted(self.recipients) != sorted(other.recipients):
      return False
    return True


class CallEvent(Event):
  """Phone calls, voicemails, video chats, etc."""
  def __init__(self, stream, format, start, end, subtype, sender, recipients, raw=None):
    super().__init__(stream, format, start, end=end, raw=raw)
    self.subtype = subtype
    self.sender = sender
    self.recipients = recipients

  def __str__(self):
    if self.subtype == 'missed':
      duration_str = ''
    else:
      duration_str = ' for '+format_time(self.end-self.start)
    return '{start} {type} {subtype}: {sender} -> {recipients}{duration}'.format(
      start=datetime.fromtimestamp(self.start).strftime('%H:%M:%S'),
      type=self.stream.capitalize(),
      subtype=self.subtype.lower(),
      sender=self.sender,
      recipients=', '.join(map(str, self.recipients)),
      duration=duration_str
    )

  def __eq__(self, other):
    if not self._generic_eq(other):
      return False
    if self.subtype != other.subtype:
      return False
    #TODO: Is this test appropriate for Contacts? Verify that if the same event is parsed from two
    #      different files, it'll end up with the same Contacts, after deduplication via ContactBook.
    if self.sender != other.sender:
      return False
    if sorted(self.recipients) != sorted(other.recipients):
      return False
    return True


class LocationEvent(Event):

  def __init__(self, stream, format, start, lat, long, accuracy, raw=None):
    super().__init__(stream, format, start, raw=raw)
    self.lat = lat
    self.long = long
    self.accuracy = accuracy


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
