"""Only published product photos may be served without a seller session."""
import json
import os
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool


def public_upload(shop, url):
    with shop._connect() as connection:
        columns = {row[1] for row in connection.execute('PRAGMA table_info(product)')}
        if 'image_url' not in columns: return False
        extra = 'extra_images' if 'extra_images' in columns else 'NULL'
        rows = connection.execute(f'SELECT image_url,{extra} AS images FROM product WHERE image_url=? OR {extra} LIKE ?', (url, '%' + url + '%'))
        for row in rows:
            if row['image_url'] == url: return True
            try:
                images = json.loads(row['images'] or '[]')
                if isinstance(images, list) and url in images: return True
            except (ValueError, TypeError): pass
    return False


class CatalogFiles(StaticFiles):
    def __init__(self, *, shop, **kwargs):
        self.shop = shop
        super().__init__(**kwargs)

    async def get_response(self, path, scope):
        normalized = os.path.normpath(path).replace('\\', '/')
        if normalized.startswith('uploads/sellerpilot/') and not await run_in_threadpool(public_upload, self.shop, '/static/' + normalized):
            raise HTTPException(404)
        return await super().get_response(path, scope)
