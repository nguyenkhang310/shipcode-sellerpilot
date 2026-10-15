from alembic import context

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine
import app.models  # noqa: F401 - expose models to Alembic metadata

target_metadata = Base.metadata
engine = build_engine(Settings().database_url)
try:
    if context.is_offline_mode():
        context.configure(url=engine.url, target_metadata=target_metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
finally:
    engine.dispose()
