"""Explicit dependency override for isolated business tests, never production."""
from app.services.auth import require_seller


def authenticated_fixture(app):
    app.dependency_overrides[require_seller] = lambda: {
        'user': {'id': 1, 'username': 'qa-seller', 'email': 'qa@example.test'},
        'shop': {'slug': 'utech-official', 'name': 'Gian hàng QA', 'role': 'owner'},
        'expires_at': '2099-01-01T00:00:00Z',
    }
