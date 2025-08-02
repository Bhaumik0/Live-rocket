# 🚀 Live Rocket Web Framework

A lightweight, production-ready web framework built from scratch in pure Python.

## ✨ Features

- **Raw Socket HTTP Server** - Custom HTTP/1.1 implementation
- **Flask-Style Routing** - Dynamic URLs with type conversion  
- **WSGI Compliant** - Production server compatibility
- **Middleware System** - Global and route-specific support
- **Template Engine** - Built-in templating system

## 🚀 Quick Start

```python
from live_rocket import live_rocket

app = live_rocket()

@app.get('/')
def home(req, res):
    res.send("Hello, Live Rocket!")

@app.get('/users/<int:user_id>')
def get_user(req, res, user_id):
    res.send(f"User ID: {user_id}")

app.run(debug=True)
