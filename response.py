import os
import re
 
class Response:
    def __init__(self, status_code="404 Not Found", text="Route not Found",app=None):
        self.status_code = status_code
        self.text = text
        self.app=app
        self.headers = [('Content-Type', 'text/plain')]
 
    def send(self, text="", status_code="200 OK"):
        self.text = str(text)
        self.status_code = f"{status_code} OK" if isinstance(status_code, int) else status_code
 
    def as_wsgi(self, start_response):
        if not self.headers:
            self.headers = [('Content-Type', 'text/plain')]
        start_response(self.status_code, self.headers)
        return [self.text.encode()]
 
    def render(self, template_name, context={}):

        project_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(project_dir, "templates")
        template_path = os.path.join(template_dir, template_name)

        if not os.path.exists(template_path):
            self.text = f"Template '{template_name}' not found in {template_dir}"
            self.status_code = "500 Internal Server Error"
            return

        with open(template_path, encoding="utf-8") as fp:
            template = fp.read()
 
        for key, value in context.items():
            template = re.sub(r'{{\s*' + re.escape(key) + r'\s*}}', str(value), template)
 
        self.__set_content_type('text/html')
        self.text = template
        self.status_code = "200 OK"
    
    def __set_content_type(self, content_type):
        updated = False
        for i, (name, _) in enumerate(self.headers):
            if name.lower() == 'content-type':
                self.headers[i] = ('Content-Type', content_type)
                updated = True
                break
        if not updated:
            self.headers.append(('Content-Type', content_type))
    
    def redirect(self,funct,peramanent=False):
        if callable(funct) and self.app:
            location=self.app.route_map.get(funct)
            if location:
                self.status_code="500 Internal server error"
                self.text="Unalbe to resolve redirect target !!!"
            
        else:
            location=str(funct)
        self.status_code="301 Moved Permanently " if peramanent else "302 Found"
        self.headers=[('Location',location)]
        self.text=f"Redirecting to {location}"
    
