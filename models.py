

#TODO: Deduplicate contacts. Instead of the drivers creating a new contact for every instance of a
#      person, there should be a single Contact instance per person. The drivers should have the
#      global contact book, and either find each person in it, or create a new one.

class Contact(object):

  def __init__(self, is_me=None, name=None, phone=None, email=None):
    self.is_me = is_me
    self.name = name
    self.phone = phone
    self.email = email

  def __hash__(self):
    return hash((self.name, self.phone, self.email))

  def __eq__(self, other):
    return hash(self) == hash(other)

  def __repr__(self):
    attr_strs = []
    for attr in ('is_me', 'name', 'phone', 'email'):
      value = getattr(self, attr)
      if value is not None:
        attr_strs.append('{}={!r}'.format(attr, value))
    return type(self).__name__+'('+', '.join(attr_strs)+')'

  def __str__(self):
    if self.is_me:
      return 'Me'
    elif self.name is not None:
      return self.name
    elif self.email is not None:
      return self.email
    elif self.phone is not None:
      return self.phone


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


class LocationEvent(Event):

  def __init__(self, stream, format, start, lat, long, accuracy, raw=None):
    super().__init__(stream, format, start, raw=raw)
    self.lat = lat
    self.long = long
    self.accuracy = accuracy
