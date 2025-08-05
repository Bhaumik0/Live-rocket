# 🚀 Live Rocket Web Framework

A lightweight, production-ready web framework built from scratch in pure Python.

## ✨ Features

- **Raw Socket HTTP Server** - Custom HTTP/1.1 implementation
- **Flask-Style Routing** - Dynamic URLs with type conversion  
- **WSGI Compliant** - Production server compatibility
- **Middleware System** - Global and route-specific support
- **Template Engine** - Built-in templating system
- 
## You can download for PIP using 

pip install live-rocket || direct from PIP website 

## 🚀 Quick Start

```python
from live_rocket import live_rocket
from ObjectMapper import Model

class MainModel(Model):
    print()

def callable_(req):
    print("Hello")
app=live_rocket(middlewares=[])

@app.get('/',middlewares=[callable_])
def hello(req,res):
    res.render("index.html")
@app.get('/edit/<name>')
def redirect(req,res,name):
    print(name)
    res.redirect(hello)   
@app.get('/upload/<file>') 
def hell(req,res,file):
    print(file)
    res.send({file})
    
if __name__ == "__main__":

    server = app.run('localhost', 8000, app)
