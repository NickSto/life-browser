from datetime import datetime

#TODO: Put stream-specific code in subclasses: Move print formatting from view.py to __str__()
#      functions, and make __eq__() functions (for deduplicating Events).

class Event(object):

  def __init__(self, stream, format, start, raw=None, **optionals):
    # stream: SMS, Calls, Chats, Location, etc
    # format: Hangouts, Voice, MyTracks, Geo Tracker, etc
    self.stream = stream
    self.format = format
    self.start = start
    if raw is None:
      self.raw = {}
    else:
      self.raw = raw


class MessageEvent(Event):

  def __init__(self, stream, format, start, sender, recipients, message, raw=None):
    super().__init__(stream, format, start, raw=raw)
    self.sender = sender
    self.recipients = recipients
    self.message = message

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


class LocationEvent(Event):

  def __init__(self, stream, format, start, lat, long, accuracy, raw=None):
    super().__init__(stream, format, start, raw=raw)
    self.lat = lat
    self.long = long
    self.accuracy = accuracy
