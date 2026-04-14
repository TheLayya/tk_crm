from slowapi import Limiter
from slowapi.util import get_remote_address

# Default limiter using IP as key, with global rate limit applied
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])

# Rate limit constants for use in route decorators
LOGIN_IP_LIMIT = "10/minute"
LOGIN_USER_LIMIT = "5/minute"
COLLECT_USER_LIMIT = "3/minute"
EXPORT_USER_LIMIT = "5/minute"
GLOBAL_IP_LIMIT = "300/minute"
