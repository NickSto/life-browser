
#TODO: Put this (along with the required attributes) into __slots__. Then you can refer to the
#      optionals inside the object with self.__slots__[3:].
#      But note that subclasses must also declare their __slots__ for it to take effect in them.
OPTIONALS = ('lat', 'long', 'accuracy', 'sender', 'recipients', 'message', 'raw')

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
    for optional in OPTIONALS:
      setattr(self, optional, optionals.get(optional))


class MessageEvent(Event):

  def __init__(self, stream, format, start, sender, recipients, message, raw=None):
    super().__init__(stream, format, start, raw=raw)
    self.sender = sender
    self.recipients = recipients
    self.message = message
