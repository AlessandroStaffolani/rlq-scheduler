import json
import pickle

import numpy as np


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return super(NumpyEncoder, self).default(obj)


def object_to_binary(obj, pickle_encoding=False):
    if pickle_encoding is True:
        return pickle.dumps(obj, protocol=pickle.DEFAULT_PROTOCOL)
    else:
        obj_str = json.dumps(obj, cls=NumpyEncoder)
        binary = ' '.join(format(ord(letter), 'b') for letter in obj_str)
        return binary.encode('utf-8')


def binary_to_object(binary, pickle_encoding=False):
    if pickle_encoding is True:
        return pickle.loads(binary)
    else:
        jsn = ''.join(chr(int(x, 2)) for x in binary.decode('utf-8').split())
        obj = json.loads(jsn)
        return obj
