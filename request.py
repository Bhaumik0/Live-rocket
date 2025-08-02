from collections import defaultdict
import urllib.parse

class Request:
    def __init__(self, environ):

        self.query_params = defaultdict(str)

        for key, val in environ.items():
            setattr(self, key.replace(".", "_").lower(), val)

        self.method = environ.get('REQUEST_METHOD', 'GET')

        query_string = environ.get('QUERY_STRING', '')
        if query_string:
            for key, val in urllib.parse.parse_qsl(query_string):
                self.query_params[key] = val

        self.path_info = environ.get('PATH_INFO', '/')

        self.body = {}
        content_length = environ.get('CONTENT_LENGTH', '')
        if content_length:
            content_length = int(content_length)
            if content_length > 0:
                request_body = environ['wsgi.input'].read(content_length)
                content_type = environ.get('CONTENT_TYPE', '')
                
                if 'application/x-www-form-urlencoded' in content_type:

                    body_data = urllib.parse.parse_qs(request_body.decode('utf-8'))
                    for key, val in body_data.items():
                        self.body[key] = val[0] if len(val) == 1 else val
                elif 'application/json' in content_type:

                    import json
                    try:
                        self.body = json.loads(request_body.decode('utf-8'))
                    except json.JSONDecodeError:
                        self.body = {}
                else:
                    self.body_raw = request_body
    
    def get_query_param(self, key, default=None):

        return self.query_params.get(key, default)
    
    def get_body_param(self, key, default=None):

        return self.body.get(key, default)