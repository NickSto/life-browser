import collections
import re

# A Contact is a subclass of a dict, with keys like 'emails' or 'addresses'.
# Each value is a ContactValues, which is also a dict subclass.
# The keys of a ContactValues are the actual phone numbers, email addresses, etc.
# Each value of a ContactValues is a ValueMetadata, yet another dict subclass.
# It maps any number of metadata keys to values, but there are (so far) two standard ones:
# `default` (bool), and `labels` (list of strings).
# To summarize, here is the structure of a Contact, as if everything were a vanilla dict:
# {
#   "names": {  # This dict is the equivalent of a ContactValues.
#     "Joe": {"default":True, "labels":[]}       # ValueMetadata.
#   },
#   "phones": {
#     "230942343": {"default":True, "labels":["Cell"]},
#     "340035954": {"default":False, labels":["Work"]}
#   },
#   "emails": {
#     "joe@cox.net": {"default":True, "labels":["Main","Home"]}
#   }
# }
# Each Contact also has an `id` and `is_me` attribute, separate from its dict data.
# API:
# contact = Contact()
# contact['phones'].add('230942343', default=True)
# contact['phones']['230942343'].labels.append('Main')


class ContactBook:

  def __init__(self):
    self._contacts = {}
    self._me = None
    self.indexable = {'names', 'phones', 'emails'}

  @property
  def me(self):
    return self._me

  @me.setter
  def me(self, value):
    self.add(value)
    self._me = value

  @property
  def indexable(self):
    return self._indexable

  @indexable.setter
  def indexable(self, keys):
    if not isinstance(keys, set):
      return TypeError(f'ContactBook.indexable must be a set. Received {type(keys)} instead.')
    self._indexable = keys
    self.reindex()

  #TODO: Make into iterable.

  def add(self, contact):
    if contact.id is None:
      contact.id = self.get_new_id()
    if contact.id in self._contacts:
      return
    self._contacts[contact.id] = contact
    if contact.is_me:
      self.me = contact
    self.index(contact)

  def replace(self, cid, contact):
    self._contacts[cid] = contact

  def get_by_id(self, cid):
    return self._contacts[cid]

  def get(self, key, value):
    try:
      return self.get_all(key, value)[0]
    except IndexError:
      return None

  def get_all(self, key, value):
    if value is None:
      return []
    index = self._indices[key]
    if value not in index:
      return []
    results = index[value]
    # Verify results.
    # Contacts could have been modified, making them no longer valid results.
    # Remove from the index and our return list.
    i = 0
    while i < len(results):
      if value in results[i][key]:
        i+=1
      else:
        del results[i]
    # Return a copy, not the original, so the user can't modify the index.
    return results.copy()

  def get_new_id(self):
    i = len(self._contacts)
    while i in self._contacts:
      i += 1
    return i

  def reindex(self):
    self._indices = collections.defaultdict(dict)
    for contact in self._contacts.values():
      self.index(contact)

  def index(self, contact):
    for key in self.indexable:
      for value in contact[key]:
        results = self._indices[key].setdefault(value, [])
        for result in results:
          if result.id == contact.id:
            return
        results.append(contact)


class Contact(dict):

  ATTR_DEFAULTS = {'id': None, 'is_me': False}

  def __init__(self, **kwargs):
    for attr, default in self.ATTR_DEFAULTS.items():
      setattr(self, attr, default)
    for key, value in kwargs.items():
      if key in self.ATTR_DEFAULTS:
        setattr(self, key, value)
      elif isinstance(value, list):
        super().__setitem__(key, ContactValues(value))
      elif value is not None:
        default = key == 'name'
        self[key+'s'].add(value, default=default)

  def __getitem__(self, key):
    if key in self:
      values = super().__getitem__(key)
    else:
      values = ContactValues()
      super().__setitem__(key, values)
    return values

  def __setitem__(self, key, values):
    raise NotImplementedError('You cannot directly set the value for a Contact key.')

  @property
  def name(self):
    values = self['names']
    if len(values) < 1:
      return None
    elif len(values) == 1:
      return list(values.keys())[0]
    else:
      for name, meta in values.items():
        if meta.default:
          return name
      return name

  @name.setter
  def name(self, value):
    if not isinstance(value, str):
      raise TypeError(f'Contact name must be a string, not {type(value)}')
    self['names'].clear()
    self['names'].add(value, default=True)

  def __str__(self):
    if self.is_me:
      return 'Me'
    elif self.name:
      return self.name
    elif self['emails']:
      return self['emails'].default
    elif self['phones']:
      return self['phones'].default
    else:
      for key, values in self.items():
        if values.default:
          return values.default
      return '???'

  def to_dict(self, **kwargs):
    data = {}
    for attr in self.ATTR_DEFAULTS:
      data[attr] = getattr(self, attr)
    all_values = {}
    for key, values in self.items():
      if values:
        all_values[key] = values.to_dict()
    data['values'] = all_values
    data.update(kwargs)
    return data

  @classmethod
  def from_dict(cls, data):
    contact = cls(id=data.get('id'), is_me=data['is_me'])
    for key, values in data['values'].items():
      for value, meta in values.items():
        contact[key].add(value, **meta)
    return contact

  #TODO: Match phone numbers that differ only by the inclusion of a plus, and/or a country code.

  @staticmethod
  def normalize_phone(raw_phone):
    """Standardize a phone number into a common format.
    At the moment, this just removes all non-numeric characters, with the exception of the
    leading plus, if any."""
    if raw_phone is None:
      return None
    normalized_phone = re.sub(r'[^0-9]', '', raw_phone)
    if raw_phone.startswith('+'):
      return '+'+normalized_phone
    else:
      return normalized_phone


class ContactValues(dict):

  def __init__(self, values=None):
    if isinstance(values, list):
      for value in values:
        self.add(value)
    elif values is not None:
      raise TypeError(f'Values must be a list, not a {type(values)}.')

  @property
  def default(self):
    first_value = None
    for value, meta in self.items():
      if first_value is None:
        first_value = value
      if meta.default:
        return value
    return first_value

  def add(self, value, default=False, label=None, labels=None):
    if label:
      if labels is not None:
        raise ValueError(f'Cannot give both label and labels.')
      labels = [label]
    if labels is None:
      labels = []
    self[value] = ValueMetadata(default=default, labels=labels)

  def remove(self, value):
    del self[value]

  def clear(self):
    for value in list(self.keys()):
      self.remove(value)

  def to_dict(self):
    data = {}
    for value, metadata in self.items():
      data[value] = metadata.to_dict()
    return data


class ValueMetadata(dict):

  def __init__(self, default=False, labels=None):
    self.default = default
    if labels is None:
      labels = []
    self.labels = labels

  @property
  def default(self):
    return self['default']

  @default.setter
  def default(self, default):
    if not isinstance(default, bool):
      raise ValueError(f'Invalid default value {default!r}. Must be True or False.')
    self['default'] = default

  @property
  def labels(self):
    return self['labels']

  @labels.setter
  def labels(self, labels):
    if not isinstance(labels, list):
      raise ValueError(f'Invalid labels {labels!r}. Must be a list of strings.')
    for label in labels:
      if not isinstance(label, str):
        raise ValueError(f'Invalid label {label!r}. Must be a string.')
    self['labels'] = labels

  @property
  def label(self):
    if len(self.labels) > 0:
      return self.labels[0]
    else:
      return None

  @label.setter
  def label(self, label):
    self.labels = [label]

  def to_dict(self):
    data = {}
    for key, value in self.items():
      data[key] = value
    return data
