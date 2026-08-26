from flask import session, redirect
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "shop_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function