
OPTIONALS = ('lat', 'long', 'accuracy', 'subtype', 'sender', 'recipients', 'message', 'raw')

class Event(object):

  def __init__(self, type, timestamp, **kwargs):
    self.type = type
    self.timestamp = timestamp
    for optional in OPTIONALS:
      setattr(self, optional, kwargs.get(optional))


def make_events(driver, paths):
  for event in driver.get_events(paths):
    kwargs = {}
    for optional in OPTIONALS:
      kwargs[optional] = event.get(optional)
    yield Event(event['type'], event['timestamp'], **kwargs)
