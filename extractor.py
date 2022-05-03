
__license__ = 'Public Domain'

import collections.abc
import itertools
import json
import sys


# copy from yt-dlp/yt-dlp
class LazyList(collections.abc.Sequence):
    ''' Lazy immutable list from an iterable
    Note that slices of a LazyList are lists and not LazyList'''

    class IndexError(IndexError):
        pass

    def __init__(self, iterable, *, reverse=False, _cache=None):
        self.__iterable = iter(iterable)
        self.__cache = [] if _cache is None else _cache
        self.__reversed = reverse

    def __iter__(self):
        if self.__reversed:
            # We need to consume the entire iterable to iterate in reverse
            yield from self.exhaust()
            return
        yield from self.__cache
        for item in self.__iterable:
            self.__cache.append(item)
            yield item

    def __exhaust(self):
        self.__cache.extend(self.__iterable)
        # Discard the emptied iterable to make it pickle-able
        self.__iterable = []
        return self.__cache

    def exhaust(self):
        ''' Evaluate the entire iterable '''
        return self.__exhaust()[::-1 if self.__reversed else 1]

    @staticmethod
    def __reverse_index(x):
        return None if x is None else -(x + 1)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            if self.__reversed:
                idx = slice(self.__reverse_index(idx.start), self.__reverse_index(idx.stop), -(idx.step or 1))
            start, stop, step = idx.start, idx.stop, idx.step or 1
        elif isinstance(idx, int):
            if self.__reversed:
                idx = self.__reverse_index(idx)
            start, stop, step = idx, idx, 0
        else:
            raise TypeError('indices must be integers or slices')
        if ((start or 0) < 0 or (stop or 0) < 0
                or (start is None and step < 0)
                or (stop is None and step > 0)):
            # We need to consume the entire iterable to be able to slice from the end
            # Obviously, never use this with infinite iterables
            self.__exhaust()
            try:
                return self.__cache[idx]
            except IndexError as e:
                raise self.IndexError(e) from e
        n = max(start or 0, stop or 0) - len(self.__cache) + 1
        if n > 0:
            self.__cache.extend(itertools.islice(self.__iterable, n))
        try:
            return self.__cache[idx]
        except IndexError as e:
            raise self.IndexError(e) from e

    def __bool__(self):
        try:
            self[-1] if self.__reversed else self[0]
        except self.IndexError:
            return False
        return True

    def __len__(self):
        self.__exhaust()
        return len(self.__cache)

    def __reversed__(self):
        return type(self)(self.__iterable, reverse=not self.__reversed, _cache=self.__cache)

    def __copy__(self):
        return type(self)(self.__iterable, reverse=self.__reversed, _cache=self.__cache)

    def __repr__(self):
        # repr and str should mimic a list. So we exhaust the iterable
        return repr(self.exhaust())

    def __str__(self):
        return repr(self.exhaust())


# copy from yt-dlp/yt-dlp
def traverse_obj(
        obj, *path_list, default=None, expected_type=None, get_all=True,
        casesense=True, is_user_input=False, traverse_string=False):
    ''' Traverse nested list/dict/tuple
    @param path_list        A list of paths which are checked one by one.
                            Each path is a list of keys where each key is a string,
                            a function, a tuple of strings/None or "...".
                            When a fuction is given, it takes the key and value as arguments
                            and returns whether the key matches or not. When a tuple is given,
                            all the keys given in the tuple are traversed, and
                            "..." traverses all the keys in the object
                            "None" returns the object without traversal
    @param default          Default value to return
    @param expected_type    Only accept final value of this type (Can also be any callable)
    @param get_all          Return all the values obtained from a path or only the first one
    @param casesense        Whether to consider dictionary keys as case sensitive
    @param is_user_input    Whether the keys are generated from user input. If True,
                            strings are converted to int/slice if necessary
    @param traverse_string  Whether to traverse inside strings. If True, any
                            non-compatible object will also be converted into a string
    # TODO: Write tests
    '''
    if not casesense:
        _lower = lambda k: (k.lower() if isinstance(k, str) else k)
        path_list = (map(_lower, variadic(path)) for path in path_list)

    def _traverse_obj(obj, path, _current_depth=0):
        nonlocal depth
        path = tuple(variadic(path))
        for i, key in enumerate(path):
            if None in (key, obj):
                return obj
            if isinstance(key, (list, tuple)):
                obj = [_traverse_obj(obj, sub_key, _current_depth) for sub_key in key]
                key = ...
            if key is ...:
                obj = (obj.values() if isinstance(obj, dict)
                       else obj if isinstance(obj, (list, tuple, LazyList))
                       else str(obj) if traverse_string else [])
                _current_depth += 1
                depth = max(depth, _current_depth)
                return [_traverse_obj(inner_obj, path[i + 1:], _current_depth) for inner_obj in obj]
            elif callable(key):
                if isinstance(obj, (list, tuple, LazyList)):
                    obj = enumerate(obj)
                elif isinstance(obj, dict):
                    obj = obj.items()
                else:
                    if not traverse_string:
                        return None
                    obj = str(obj)
                _current_depth += 1
                depth = max(depth, _current_depth)
                return [_traverse_obj(v, path[i + 1:], _current_depth) for k, v in obj if try_call(key, args=(k, v))]
            elif isinstance(obj, dict) and not (is_user_input and key == ':'):
                obj = (obj.get(key) if casesense or (key in obj)
                       else next((v for k, v in obj.items() if _lower(k) == key), None))
            else:
                if is_user_input:
                    key = (int_or_none(key) if ':' not in key
                           else slice(*map(int_or_none, key.split(':'))))
                    if key == slice(None):
                        return _traverse_obj(obj, (..., *path[i + 1:]), _current_depth)
                if not isinstance(key, (int, slice)):
                    return None
                if not isinstance(obj, (list, tuple, LazyList)):
                    if not traverse_string:
                        return None
                    obj = str(obj)
                try:
                    obj = obj[key]
                except IndexError:
                    return None
        return obj

    if isinstance(expected_type, type):
        type_test = lambda val: val if isinstance(val, expected_type) else None
    elif expected_type is not None:
        type_test = expected_type
    else:
        type_test = lambda val: val

    for path in path_list:
        depth = 0
        val = _traverse_obj(obj, path)
        if val is not None:
            if depth:
                for _ in range(depth - 1):
                    val = itertools.chain.from_iterable(v for v in val if v is not None)
                val = [v for v in map(type_test, val) if v is not None]
                if val:
                    return val if get_all else val[0]
            else:
                val = type_test(val)
                if val is not None:
                    return val
    return default


# copy from yt-dlp/yt-dlp
def variadic(x, allowed_types=(str, bytes, dict)):
    return x if isinstance(x, collections.abc.Iterable) and not isinstance(x, allowed_types) else (x,)


# copy from yt-dlp/yt-dlp
def int_or_none(v, scale=1, default=None, get_attr=None, invscale=1):
    if get_attr and v is not None:
        v = getattr(v, get_attr, None)
    try:
        return int(v) * invscale // scale
    except (ValueError, TypeError, OverflowError):
        return default


# copy from yt-dlp/yt-dlp
def try_call(*funcs, expected_type=None, args=[], kwargs={}):
    for f in funcs:
        try:
            val = f(*args, **kwargs)
        except (AttributeError, KeyError, TypeError, IndexError, ZeroDivisionError):
            pass
        else:
            if expected_type is None or isinstance(val, expected_type):
                return val


def nanoseconds_to_time(nanoseconds):
    time = int(nanoseconds / 1000000)
    seconds = time % 60
    minutes = int(time / 60)
    hour = int(time / 3600)
    miliseconds = int(nanoseconds / 1000) % 1000
    return '%02d:%02d:%02d,%03d' % (hour, minutes, seconds, miliseconds)


def convert_to_str_array(chat_lines, index, last=False):
    item = chat_lines[index]
    start = item['timestamp'] - first_timestamp
    message = '%s: %s' % (item['author'], item['text'])
    if not last:
        duration = min(max_duration, chat_lines[index + 1]['timestamp'] - item['timestamp'])
    else:
        duration = max_duration
    timecodes = '%s --> %s' % (nanoseconds_to_time(start), nanoseconds_to_time(start + duration))
    return {
        'timecodes':timecodes,
        'message':message
    }


if sys.argv[1] is None:
    sys.exit('File must be used as first parameter.')

chat_lines = []
first_timestamp = None
max_duration = 10000000

try:
    with open(sys.argv[1], encoding='utf-8', errors='ignore') as cf:
        while True:
            line = cf.readline()
            if not line:
                break

            chat_item = traverse_obj(json.loads(line),('replayChatItemAction','actions',0,'addChatItemAction','item','liveChatTextMessageRenderer'))
            if chat_item is None:
                continue
            message = ''
            for item in traverse_obj(chat_item,('message','runs')):
                if item.get('text'):
                    message += '%s ' % item.get('text')
            timestamp = int_or_none(chat_item.get('timestampUsec'))
            entrie = {
                'text': message.strip(),
                'author': traverse_obj(chat_item, ('authorName', 'simpleText')),
                'timestamp': timestamp,
            }
            if timestamp is not None and message != '':
                if first_timestamp is None:
                    first_timestamp = timestamp
                chat_lines.append(entrie)
except OSError:
    sys.exit('ERROR: chat file %s could not be read' % sys.argv[1])

chat_lines = sorted(chat_lines, key=lambda x:x['timestamp'])
out_items = []
count = 0
while count < len(chat_lines) - 1:
    out_items.append(convert_to_str_array(chat_lines, count))
    count += 1
out_items.append(convert_to_str_array(chat_lines, count, True))
del(chat_lines)
count = 1
with open('%s.srt' % sys.argv[1], 'w', encoding='utf-8', errors='ignore') as fp:
    for item in out_items:
        fp.write(str(count) + '\n')
        fp.write(item['timecodes'] + '\n')
        fp.write(item['message'] + '\n')
        fp.write('\n')
        count += 1
