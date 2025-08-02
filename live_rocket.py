import inspect
from request import Request
from response import Response
from parse import parse
import types
from typing import Any
import socket
import threading
import urllib.parse
from io import StringIO
import sys
import re
from typing import Dict, Any, Optional, Tuple

supported_request_methods = {'GET', 'POST', 'DELETE','PUT','PATCH'}
 
class SocketHTTPServer:
    def __init__(self, app, host='localhost', port=8000):
        self.app = app
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
    
    def start(self):
        """Start the HTTP server using raw sockets"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen(5) 
            self.running = True
            
            
            print("Press Ctrl+C to stop the server")
            
            while self.running:
                try:
                    client_socket, client_address = self.socket.accept()

                    thread = threading.Thread(
                        target=self.handle_request,
                        args=(client_socket, client_address)
                    )
                    thread.daemon = True
                    thread.start()
                    
                except OSError:
                    if self.running:
                        print("❌ Socket error occurred")
                    break
                    
        except KeyboardInterrupt:
            print("\n🛑 Shutting down server...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the server and close socket"""
        self.running = False
        if self.socket:
            self.socket.close()
    
    def handle_request(self, client_socket, client_address):
        """Handle individual HTTP request"""
        try:

            request_data = client_socket.recv(4096).decode('utf-8')
            
            if not request_data:
                return
            

            environ = self.parse_http_request(request_data, client_address)

            response_data = self.handle_wsgi_request(environ)

            client_socket.send(response_data)
            
        except Exception as e:
            error_response = self.create_error_response(500, str(e))
            client_socket.send(error_response)
            
        finally:
            client_socket.close()
    
    def parse_http_request(self, request_data, client_address):
        """Parse raw HTTP request into WSGI environ dict"""
        lines = request_data.split('\r\n')

        request_line = lines[0]
        method, path, protocol = request_line.split(' ')

        if '?' in path:
            path, query_string = path.split('?', 1)
        else:
            query_string = ''

        headers = {}
        i = 1
        while i < len(lines) and lines[i]:
            header_line = lines[i]
            if ':' in header_line:
                key, value = header_line.split(':', 1)
                headers[key.strip().upper().replace('-', '_')] = value.strip()
            i += 1
        body_start = i + 1
        body = '\r\n'.join(lines[body_start:]) if body_start < len(lines) else ''

        environ = {
            'REQUEST_METHOD': method,
            'PATH_INFO': urllib.parse.unquote(path),
            'QUERY_STRING': query_string,
            'CONTENT_TYPE': headers.get('CONTENT_TYPE', ''),
            'CONTENT_LENGTH': headers.get('CONTENT_LENGTH', ''),
            'SERVER_NAME': self.host,
            'SERVER_PORT': str(self.port),
            'REMOTE_ADDR': client_address[0],
            'REMOTE_HOST': client_address[0],
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': StringIO(body),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': True,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
        }
        
        # Add HTTP headers to environ
        for key, value in headers.items():
            if key not in ['CONTENT_TYPE', 'CONTENT_LENGTH']:
                environ[f'HTTP_{key}'] = value
        
        return environ
    
    def handle_wsgi_request(self, environ):
        """Handle request using WSGI application"""
        response_parts = []
        status = None
        headers = None
        
        def start_response(response_status, response_headers, exc_info=None):
            nonlocal status, headers
            status = response_status
            headers = response_headers

        try:
            response_iter = self.app(environ, start_response)

            for data in response_iter:
                if isinstance(data, str):
                    response_parts.append(data.encode('utf-8'))
                else:
                    response_parts.append(data)
            return self.build_http_response(status, headers, b''.join(response_parts))
            
        except Exception as e:
            return self.create_error_response(500, f"Internal Server Error: {str(e)}")
    
    def build_http_response(self, status, headers, body):
        """Build complete HTTP response"""
        response_lines = [f"HTTP/1.1 {status}"]

        for header_name, header_value in headers:
            response_lines.append(f"{header_name}: {header_value}")
        

        has_content_length = any(h[0].lower() == 'content-length' for h in headers)
        if not has_content_length:
            response_lines.append(f"Content-Length: {len(body)}")

        response_lines.append("Connection: close")

        response_header = '\r\n'.join(response_lines) + '\r\n\r\n'
        return response_header.encode('utf-8') + body
    
    def create_error_response(self, status_code, message):
        """Create HTTP error response"""
        status_messages = {
            400: "Bad Request",
            404: "Not Found", 
            500: "Internal Server Error"
        }
        
        status_text = status_messages.get(status_code, "Error")
        body = f"<h1>{status_code} {status_text}</h1><p>{message}</p>".encode('utf-8')
        
        response = f"""HTTP/1.1 {status_code} {status_text}\r
Content-Type: text/html\r
Content-Length: {len(body)}\r
Connection: close\r
\r
""".encode('utf-8') + body
        
        return response


class URLPattern:
    """Handle URL pattern matching and parameter extraction"""
    
    def __init__(self, pattern: str):
        self.pattern = pattern
        self.regex_pattern = None
        self.parameter_names = []
        self._compile_pattern()
    
    def _compile_pattern(self):
        """Convert Flask-style pattern to regex"""
 
        parameter_regex = r'<(?:([^:>]+):)?([^>]+)>'
        
        regex_pattern = self.pattern
        

        for match in re.finditer(parameter_regex, self.pattern):
            param_type = match.group(1) or 'string'  
            param_name = match.group(2)
            
            self.parameter_names.append((param_name, param_type))
            

            type_patterns = {
                'string': r'([^/]+)',    
                'int': r'(\d+)',           
                'float': r'(\d+\.?\d*)',   
                'path': r'(.+)',           
                'uuid': r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
            }
            
            type_pattern = type_patterns.get(param_type, r'([^/]+)')
            regex_pattern = regex_pattern.replace(match.group(0), type_pattern, 1)
        

        self.regex_pattern = f'^{regex_pattern}$'
    
    def match(self, url: str) -> Optional[Dict[str, Any]]:
        """Match URL against pattern and return parameters"""
        if not self.regex_pattern:
            return {} if url == self.pattern else None
        
        match = re.match(self.regex_pattern, url)
        if not match:
            return None

        params = {}
        for i, (param_name, param_type) in enumerate(self.parameter_names):
            raw_value = match.group(i + 1)
            

            try:
                if param_type == 'int':
                    params[param_name] = int(raw_value)
                elif param_type == 'float':
                    params[param_name] = float(raw_value)
                else:
                    params[param_name] = raw_value
            except (ValueError, TypeError):

                return None
        
        return params


class RouteManager:
    """Enhanced route management with dynamic URL support"""
    
    def __init__(self):
        self.static_routes = {}     
        self.dynamic_routes = []     
    
    def add_route(self, pattern: str, method: str, handler, middlewares=None):
        """Add a route with support for dynamic URLs"""
        middlewares = middlewares or []

        if '<' in pattern and '>' in pattern:

            url_pattern = URLPattern(pattern)
            self.dynamic_routes.append({
                'pattern': url_pattern,
                'original_pattern': pattern,
                'method': method,
                'handler': handler,
                'middlewares': middlewares
            })
        else:

            if pattern not in self.static_routes:
                self.static_routes[pattern] = {}
            self.static_routes[pattern][method] = {
                'handler': handler,
                'middlewares': middlewares
            }
    
    def find_route(self, path: str, method: str) -> Tuple[Optional[Any], Dict[str, Any], list]:
        """Find matching route and return handler, params, and middlewares"""

        if path in self.static_routes and method in self.static_routes[path]:
            route_info = self.static_routes[path][method]
            return route_info['handler'], {}, route_info['middlewares']
        

        for route in self.dynamic_routes:
            if route['method'] == method:
                params = route['pattern'].match(path)
                if params is not None:
                    return route['handler'], params, route['middlewares']
        
        return None, {}, []


class live_rocket:
    def __init__(self, middlewares=[]) -> None:
        self.route_manager = RouteManager() 
        self.middlewares = middlewares
        self.route_map = {} 
        

        self.routes = {}
        self.middlewares_for_route = {}
        
    def __call__(self, environ, start_response) -> Any:
        from response import Response
        from request import Request
        import types
        
        response = Response(app=self)
        request = Request(environ)


        for middleware in self.middlewares:
            if isinstance(middleware, types.FunctionType):
                middleware(request)
            else:
                raise ValueError("You can pass function as middlewares !")


        handler, params, route_middlewares = self.route_manager.find_route(
            request.path_info, request.method
        )
        
        if handler:

            for mw in route_middlewares:
                if isinstance(mw, types.FunctionType):
                    mw(request)
                else:
                    raise ValueError("You can pass only function as middlewares !!")
            

            handler(request, response, **params)
            return response.as_wsgi(start_response)
        

        response = Response(status_code="404 Not Found", text="Route not found")
        return response.as_wsgi(start_response)
    
    def route_common(self, path, handler, method_name, middlewares):

        path_name = path or f"/{handler.__name__}"

        self.route_map[handler] = path_name

        self.route_manager.add_route(path_name, method_name, handler, middlewares)

        if path_name not in self.routes:
            self.routes[path_name] = {}
        self.routes[path_name][method_name] = handler
        
        if path_name not in self.middlewares_for_route:
            self.middlewares_for_route[path_name] = {}
        self.middlewares_for_route[path_name][method_name] = middlewares
        
        return handler
    
    def get(self, path=None, middlewares=[]):
        def wrapper(handler):
            return self.route_common(path, handler, 'GET', middlewares)
        return wrapper
    
    def post(self, path=None, middlewares=[]):
        def wrapper(handler):
            return self.route_common(path, handler, 'POST', middlewares)
        return wrapper
    
    def put(self, path=None, middlewares=[]):
        def wrapper(handler):
            return self.route_common(path, handler, 'PUT', middlewares)
        return wrapper
    
    def delete(self, path=None, middlewares=[]):
        def wrapper(handler):
            return self.route_common(path, handler, 'DELETE', middlewares)
        return wrapper
    
    def patch(self, path=None, middlewares=[]):
        def wrapper(handler):
            return self.route_common(path, handler, 'PATCH', middlewares)
        return wrapper
    
    def route(self, path=None, middlewares=[]):
        """Class-based route decorator"""
        import inspect
        supported_request_methods = {'GET', 'POST', 'DELETE', 'PUT', 'PATCH'}
        
        def wrapper(handler):
            if isinstance(handler, type):
                class_members = inspect.getmembers(
                    handler,
                    lambda x: inspect.isfunction(x) and 
                              not (x.__name__.startswith("__") and x.__name__.endswith("__")) and 
                              x.__name__.upper() in supported_request_methods
                )
                for fn_name, fn_handler in class_members:
                    self.route_common(path or f"/{handler.__name__}", fn_handler, fn_name.upper(), middlewares)
            else:
                raise ValueError("@route can only be used for classes")
            return handler 
        return wrapper
    
    def url_for(self, handler_func, **params):
        """Generate URL for a handler function with parameters"""
        if handler_func not in self.route_map:
            raise ValueError(f"No route found for handler {handler_func.__name__}")
        
        pattern = self.route_map[handler_func]

        url = pattern
        for param_name, param_value in params.items():
            param_patterns = [
                f'<{param_name}>',
                f'<string:{param_name}>',
                f'<int:{param_name}>',
                f'<float:{param_name}>',
                f'<path:{param_name}>',
                f'<uuid:{param_name}>'
            ]
            
            for param_pattern in param_patterns:
                if param_pattern in url:
                    url = url.replace(param_pattern, str(param_value))
                    break
        
        return url
    
    def run(self, host='localhost', port=8000, debug=False, reload=False, use_socket=True):
        """Start the development server with socket support"""
        print(f"🚀 Live Rocket Socket Server at http://{host}:{port}")
        if debug:
            print("🔧 Debug mode: ON")
        
        if use_socket:
            server = SocketHTTPServer(self, host, port)
            server.start()
        else:
            from wsgiref.simple_server import make_server
            if debug:
                print("📡 Using WSGI reference server")
            server = make_server(host, port, self)
            
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("\n🛑 Server shutting down...")
                server.shutdown()