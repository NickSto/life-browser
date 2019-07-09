
########## Shims for a Django-independent environment. ##########

class ModelsStub:
  class Model:
    def __init__(self, **kwargs):
      for name, value in kwargs.items():
        setattr(self, name, value)
  def __getattr__(self, attr_name):
    return FieldStubMaker(attr_name)

models = ModelsStub()


class FieldStub:
  def __init__(self, name, *args, **kwargs):
    self.name = name
    self.args = args
    self.kwargs = kwargs
  def __repr__(self):
    output = '{}('.format(self.name)
    args_str = ', '.join([repr(arg) for arg in self.args])
    if args_str:
      output += args_str
    kwargs_str = ', '.join(['{}={!r}'.format(key, value) for key, value in self.kwargs.items()])
    if kwargs_str:
      if args_str:
        output += ', '+kwargs_str
      else:
        output += kwargs_str
    return output+')'


class FieldStubMaker:
  def __init__(self, name):
    self.name = name
  def __call__(self, *args, **kwargs):
    return FieldStub(self.name, *args, **kwargs)
