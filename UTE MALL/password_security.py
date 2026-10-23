"""Fail closed when an account's hash is corrupt or its algorithm unavailable."""
import logging
from werkzeug.security import check_password_hash as werkzeug_check_password_hash


def check_password_hash(digest, password):
    try:
        return werkzeug_check_password_hash(digest, password)
    except (AttributeError, ValueError, TypeError, OverflowError) as error:
        # Never log the hash, salt, password, or raw exception arguments.
        logging.getLogger(__name__).warning('Password verification unavailable: %s', type(error).__name__)
        return False
