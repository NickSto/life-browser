from datetime import datetime
import re


class ContactBook(list):
  def __init__(self):
    self.me = Contact(is_me=True)
    self.indices = {'name':{}, 'phones':{}, 'emails':{}}

  def add(self, contact):
    """Add a Contact to the ContactBook, unless it's already in it.
    WARNING: This checks for membership with an exact match, so if you create a new Contact with
    the same name, phone, etc, but one attribute is different, it won't recognize them as the same.
    """
    if contact in self:
      return
    contact.book = self
    self.append(contact)
    self.index(contact)

  def index(self, contact):
    #TODO: Remove contacts from the index if an attribute is deleted?
    for key, contact_value in contact.items():
      if not contact_value.indexable:
        continue
      # Get and/or create the index.
      if key in self.indices:
        index = self.indices[key]
      else:
        index = {}
        self.indices[key] = index
      # Collect the values to index by.
      indexable_values = []
      if isinstance(contact_value, ContactValues):
        for subvalue in contact_value:
          indexable_values.append(subvalue.value)
      else:
        indexable_values.append(contact_value.value)
      # Add to the index.
      for value in indexable_values:
        hits = index.get(value, [])
        if not contact.foundIn(hits):
          hits.append(contact)
        index[value] = hits

  def findDuplicates(self, contact):
    """Try to find a duplicate contact by its indexable fields."""
    hits = []
    for key, contact_value in contact.items():
      if not contact_value.indexable:
        continue
      index = self.indices.get(key)
      if not index:
        continue
      # Collect the values to search by.
      searchable_values = []
      if isinstance(contact_value, ContactValues):
        plural = True
        for subvalue in contact_value:
          searchable_values.append(subvalue.value)
      else:
        plural = False
        searchable_values.append(contact_value.value)
      for value in searchable_values:
        for hit in index.get(value, ()):
          if not hit.foundIn(hits):
            # Verify the hit. The index could be out of sync with the actual values in the contacts,
            # so make sure the contact actualy has the value.
            if (plural and value in hit[key]) or (not plural and value == hit[key]):
              hits.append(hit)
    return hits

  def findDuplicate(self, contact):
    hits = self.findDuplicates(contact)
    if hits:
      return hits[0]
    else:
      return None

  def add_or_merge(self, contact):
    """If the `Contact` has no match in the book, add it. Otherwise, add its info to the existing
    `Contact`s. Return either this `Contact` (if it was added), or the first existing `Contact`
    (if it was merged)."""
    duplicates = self.findDuplicates(contact)
    if duplicates:
      for duplicate in duplicates:
        duplicate.add(contact)
      return duplicates[0]
    else:
      self.add(contact)
      return contact

  def getAll(self, key, value):
    if value is None:
      return []
    if key not in self.indices:
      return []
    return self.indices[key].get(value, [])

  def getOne(self, key, value):
    results = self.getAll(key, value)
    if results:
      return results[0]
    else:
      return None


class Contact(dict):

  def __init__(self, book=None, is_me=None, name=None, phone=None, email=None, **kwargs):
    # The ContactBook containing this contact.
    self.book = book
    self.is_me = is_me
    self.name = name
    self['phones'] = ContactValues(contact=self, key='phones', indexable=True)
    self['emails'] = ContactValues(contact=self, key='emails', indexable=True)
    self.phone = phone
    self.email = email
    # Add any other key/value items given to the constructor.
    for key, value in kwargs.items():
      self[key] = value

  @property
  def name(self):
    return self['name']

  @name.setter
  def name(self, value):
    self['name'] = value
    self['name'].indexable = True

  @property
  def phone(self):
    self.get_by_index('phones', 0)

  # Setting .phone or .email won't overwrite anything, but instead insert the value at the front
  # of the list and push the rest down the list.
  @phone.setter
  def phone(self, value):
    self['phones'].insert(0, value)

  @property
  def email(self):
    self.get_by_index('emails', 0)

  @email.setter
  def email(self, value):
    self['emails'].insert(0, value)

  def get_by_index(self, key, index):
    """Get the first value of the ContactValues list at `key`."""
    contact_value = self.get(key)
    if isinstance(contact_value, ContactValues) and len(contact_value) > index:
      return contact_value[index].value
    else:
      return None

  def reindex(self):
    if self.book:
      self.book.index(self)

  @staticmethod
  def normalize_phone(raw_phone):
    normalized_phone = re.sub(r'[^0-9]', '', raw_phone)
    if raw_phone.startswith('+'):
      return '+'+normalized_phone
    else:
      return normalized_phone

  def has_overlap(self, other):
    """Is there a match between the values of this contact and the values of the other one?"""
    for key, other_value in other.items():
      our_value = self.get(key)
      if our_value is None:
        continue
      else:
        our_plural = isinstance(our_value, ContactValues)
        other_plural = isinstance(other_value, ContactValues)
        if our_plural and other_plural:
          our_values = our_value
          other_values = other_value
          for our_value in our_values:
            if other_values.find(our_value):
              return True
        elif not our_plural and not other_plural:
          if our_value.value == other_value.value:
            return True
    return False

  def add(self, other):
    """Add the data from another Contact into this one.
    In conflicts, keep the existing data.
    ContactValue:
      If the key doesn't have a value in this instance, but does in the other, take the other one.
      If there is a value in both, and the underlying raw value is the same, take the attributes of
      the other according to ContactValue.add().
    ContactValues:
      If an item from the other's list doesn't exist in ours, add it to ours.
      See ContactValues.add() for details and rules on duplicates.
    """
    #TODO: Save conflicting single `ContactValue`s somewhere.
    # Special attributes.
    self.is_me = self.is_me or other.is_me
    self.book = self.book or other.book
    # Generic key/values.
    for key, contact_value in other.items():
      if key not in self:
        self[key] = contact_value
        continue
      if isinstance(contact_value, ContactValues):
        # Merge ContactValues list.
        self[key].add(contact_value)
      elif self[key] != contact_value and self[key].value == contact_value.value:
        # Add attributes from the other ContactValue.
        self[key].add(contact_value)

  def foundIn(self, contacts):
    """Faster way of finding a `Contact` in a list of `Contact`s than `contact in contacts`."""
    # Use a single value to scan through the list of contacts, checking if each has that value.
    # A true match must have that value, so it won't be missed.
    # True negatives should be quickly eliminated without going through the whole normalization
    # process required by a full `==` comparison.
    # Then, after you've found a candidate, do a full `==` to check it.
    # The best hook value would be the name.
    if self.name:
      hook = self.name
      hook_key = 'name'
    else:
      # Otherwise, we'd prefer a singular ContactValue.
      # Only fall back to a ContactValues list if there are no singluar values.
      hook = None
      hook_key = None
      backup_hook = None
      backup_key = None
      for key, contact_value in self.items():
        if isinstance(contact_value, ContactValues):
          backup_hook = contact_value
          backup_key = key
        else:
          hook = contact_value
          hook_key = key
          break
    # Once you've found your hook(s), scan for matches.
    if hook:
      key = hook_key
      value = hook.value
      for contact in contacts:
        if key in contact and contact[key].value == value:
          # Verify the candidate match.
          if contact == self:
            return True
    elif backup_hook:
      key = backup_key
      values = backup_hook.values
      for contact in contacts:
        if key in contact:
          for value in contact[key].values:
            if value in values:
              # Verify the candidate match.
              if contact == self:
                return True
    else:
      # We have no values? I guess the user wants to find more empty Contacts?
      # Fall back to old method.
      return self in contacts
    return False

  def _normalize(self):
    data = [self.is_me]
    for key in sorted(self.keys()):
      norm_value = self[key]._normalize()
      data.append((key, norm_value))
    return tuple(data)

  def __eq__(self, other):
    if self.is_me != other.is_me:
      return False
    if len(self) != len(other):
      return False
    for key, contact_value in self.items():
      if other.get(key) != contact_value:
        return False
    return True

  def __setitem__(self, key, value):
    old_value = self.get(key)
    contact_value = ContactValue.get_wrapped(value, contact=self, key=key)
    if old_value:
      contact_value.indexable = old_value.indexable
    super().__setitem__(key, contact_value)
    self.reindex()

  #TODO: Other ways of setting values like setdefault() and update().

  def __repr__(self):
    value_strs = []
    for key, contact_value in self.items():
      if not contact_value:
        continue
      if not contact_value.indexable:
        continue
      value = None
      if isinstance(contact_value, ContactValues):
        for this_value in contact_value:
          if this_value:
            value = this_value
            break
      elif isinstance(contact_value, ContactValue):
        value = contact_value.value
      else:
        value = contact_value
      if value is not None:
        value_strs.append('{} {!r}'.format(key, value))
    type_str = type(self).__name__
    return '<{}: {}>'.format(type_str, ', '.join(value_strs))

  def __str__(self):
    if self.is_me:
      return 'Me'
    elif self.name.value:
      return str(self.name)
    elif self.emails:
      return str(self.emails[0])
    elif self.phones:
      return str(self.phones[0])


# Observed types of values in VCARDs:
# N (name), FN (formal name?), EMAIL, TEL, ADR, BDAY, ORG, NOTE, URL, PHOTO, X-PHONETIC-LAST-NAME,
# and X-ANDROID-CUSTOM (nickname and relation).

class ContactValue(object):

  def __init__(self, contact=None, key=None, value=None, indexable=False, attributes=None):
    self.contact = contact
    self.key = key
    self.value = value
    self.indexable = indexable
    if attributes is None:
      self.attributes = {}
    else:
      self.attributes = attributes

  @classmethod
  def get_raw(cls, input_value):
    if isinstance(input_value, cls):
      return input_value.value
    else:
      return input_value

  @classmethod
  def get_wrapped(cls, input_value, **kwargs):
    if isinstance(input_value, cls):
      return input_value
    else:
      return cls(value=input_value, **kwargs)

  def add(self, other):
    """Absorb the attributes of another ContactValue, preferring our own when they conflict."""
    self.contact = self.contact or other.contact
    self.key = self.key or other.key
    self.value = self.value or other.value
    for key, value in other.attributes.items():
      if key not in self.attributes:
        self.attributes[key] = value

  def _normalize(self):
    return (self.key, self.value, self.indexable, self.attributes)

  def __eq__(self, other):
    if isinstance(other, ContactValue):
      return self._normalize() == other._normalize()
    else:
      return self.value == other

  def __bool__(self):
    return bool(self.value)

  def __str__(self):
    return str(self.value)

  def __repr__(self):
    attr_strs = []
    for attr in ('key', 'value', 'indexable', 'attributes'):
      if not hasattr(self, attr):
        continue
      value = getattr(self, attr)
      if attr != 'value' and value is None or (attr == 'attributes' and value == {}):
        continue
      attr_strs.append('{}={!r}'.format(attr, value))
    type_str = type(self).__name__
    return '{}({})'.format(type_str, ', '.join(attr_strs))


class ContactValues(ContactValue, list):

  def __init__(self, contact=None, key=None, values=(), indexable=False):
    super().__init__(contact=contact, key=key, indexable=indexable)
    # The ContactValues index allows quick searching of the list of values by raw value.
    # Unlike the ContactBook index, it should be kept up to date and have zero false positives and
    # negatives.
    self.index = {}
    self.values = values

  @property
  def values(self):
    raw_values = []
    for contact_value in self:
      raw_values.append(contact_value.value)
    return raw_values

  @values.setter
  def values(self, input_values):
    super().clear()
    for input_value in input_values:
      contact_value = ContactValue.get_wrapped(input_value)
      self.append(contact_value)
    self.reindex()

  def reindex(self):
    self.index = {}
    for contact_value in self.values:
      self.index[contact_value.value] = contact_value

  def find(self, input_value):
    """Look up a ContactValue by raw value."""
    raw_value = ContactValue.get_raw(input_value)
    return self.index.get(raw_value)

  def add(self, other):
    """Merge the values from another ContactValues into ourself.
    If we find duplicates, absorb the attributes of the other one when they don't conflict with ours.
    """
    for other_value in other:
      our_value = self.find(other_value)
      if our_value:
        # If we find a duplicate, absorb the others' attributes when they don't conflict with ours.
        if our_value != other_value:
          our_value.contact = our_value.contact or other_value.contact
          our_value.key = our_value.key or other_value.key
          for key, value in other_value.attributes.items():
            if key not in our_value.attributes:
              our_value.attributes[key] = value
      else:
        self.append(other_value)

  def _normalize(self):
    norm_values = tuple([val._normalize() for val in self])
    return (self.key, self.indexable, norm_values)

  def __eq__(self, other):
    if len(self) != len(other):
      return False
    if self.key != other.key or self.indexable != other.indexable:
      return False
    for our_value, other_value in zip(self, other):
      if our_value != other_value:
        return False
    return True

  # Overriding list methods:

  #   Adding values:

  def append(self, input_value):
    contact_value = ContactValue.get_wrapped(input_value)
    super().append(contact_value)
    self.index_and_reindex(contact_value)

  def extend(self, input_values):
    contact_values = []
    for input_value in input_values:
      contact_value = ContactValue.get_wrapped(input_value)
      contact_values.append(contact_value)
      self.index[contact_value.value] = contact_value
    super().extend(contact_values)
    if self.contact:
      self.contact.reindex()

  def insert(self, index, input_value):
    contact_value = ContactValue.get_wrapped(input_value)
    super().insert(index, contact_value)
    self.index_and_reindex(contact_value)

  def __setitem__(self, index, input_value):
    contact_value = ContactValue.get_wrapped(input_value)
    super().__setitem__(index, contact_value)
    self.index_and_reindex(contact_value)

  def index_and_reindex(self, contact_value):
    self.index[contact_value.value] = contact_value
    if self.contact:
      self.contact.reindex()

  #   Removing values:

  def __delitem__(self, index):
    super().__delitem__(index)
    self.reindex()

  def remove(self, input_value):
    contact_value = ContactValue.get_wrapped(input_value)
    super().remove(contact_value)
    self.reindex()

  def pop(self, *args):
    super().pop(*args)
    self.reindex()

  def clear(self):
    super().clear()
    self.index = {}

  def __contains__(self, value):
    if isinstance(value, ContactValue):
      return super().__contains__(value)
    else:
      return bool(self.find(value))

  def __str__(self):
    return ', '.join([str(v) for v in self])

  #TODO: __repr__


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