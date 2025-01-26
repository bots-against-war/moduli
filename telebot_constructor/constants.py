# for scoping stores, e.g. when used in a larger app
from multidict import istr

CONSTRUCTOR_PREFIX = "telebot-constructor"

CONSTRUCTOR_HEADER_PREFIX = "X-Telebot-Constructor"
FILENAME_HEADER = istr(f"{CONSTRUCTOR_HEADER_PREFIX}-Filename")
TRUSTED_CLIENT_TOKEN_HEADER = istr(f"{CONSTRUCTOR_HEADER_PREFIX}-Trusted-Client")
TRUSTED_CLIENT_USER_ID_HEADER = istr(f"{CONSTRUCTOR_HEADER_PREFIX}-User-Id")
