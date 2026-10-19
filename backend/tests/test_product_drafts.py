import base64
import json
import sqlite3
from pathlib import Path
import pytest

from fastapi.testclient import TestClient

from app.ai.contracts import AIProviderError, ProviderHealth
from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
import app.models  # noqa: F401


class OfflineProvider:
    async def check_health(self):
        return ProviderHealth(availability="unavailable")

    async def classify(self, _message, *, today):
        raise AIProviderError("provider_unavailable")

    async def respond(self, _message, *, history, facts):
        raise AIProviderError("provider_unavailable")


class CopyProvider(OfflineProvider):
    provider = 'ollama'
    model = 'test-copy-model'

    def __init__(self):
        self.calls = []

    async def respond(self, message, *, history, facts):
        self.calls.append({'message': message, 'history': history, 'facts': facts})
        if not facts['name']:
            return json.dumps({'name': None, 'description': None, 'category_id': None,
                               'clarification': 'Bạn đang bán sản phẩm gì? Cho mình vài đặc điểm nhé.'})
        return json.dumps({'name': facts['name'],
                           'description': f"{facts['name']} hiện có tại gian hàng. Bạn có thể xem hình ảnh sản phẩm để lựa chọn trước khi đặt mua.",
                           'category_id': facts['category_id'], 'clarification': None})


def build_shop(path: Path):
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE shop (
              id INTEGER PRIMARY KEY, slug TEXT, name TEXT, location TEXT, status TEXT
            );
            CREATE TABLE category (
              id INTEGER PRIMARY KEY, name TEXT, display_order INTEGER
            );
            CREATE TABLE product (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT,
              price REAL NOT NULL, old_price REAL, image_url TEXT, extra_images TEXT,
              category_id INTEGER NOT NULL,
              is_new INTEGER, is_on_sale INTEGER, stock INTEGER, created_at TEXT,
              sku TEXT UNIQUE, slug TEXT UNIQUE, source TEXT, source_id TEXT, currency TEXT,
              rating REAL, rating_count INTEGER, status TEXT, shop_id INTEGER,
              sold_count INTEGER, historical_sold_count INTEGER, location TEXT, is_featured INTEGER
            );
            CREATE TABLE product_variant (
              id INTEGER PRIMARY KEY, product_id INTEGER, sku TEXT UNIQUE, title TEXT,
              size TEXT, color TEXT, price REAL, old_price REAL, stock INTEGER, is_active INTEGER
            );
            CREATE TABLE "order" (
              id INTEGER PRIMARY KEY, shop_id INTEGER, total_amount REAL, status TEXT, created_at TEXT
            );
            CREATE TABLE order_item (
              id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, price REAL
            );
            CREATE TABLE seller_activity (
              id INTEGER PRIMARY KEY, shop_id INTEGER, user_id INTEGER, action TEXT, created_at TEXT
            );
            INSERT INTO shop VALUES (1, 'utech-official', 'UTech Official', 'TP. Hồ Chí Minh', 'active');
            INSERT INTO category VALUES
              (2, 'Thời Trang Nam', 1),
              (3, 'Điện Thoại & Phụ Kiện', 2),
              (4, 'Máy Tính & Laptop', 3),
              (7, 'Nhà Cửa & Đời Sống', 4);
            INSERT INTO product (
              id, name, price, category_id, stock, sku, slug, source, currency,
              rating, rating_count, status, shop_id, sold_count, historical_sold_count, location, is_featured
            ) VALUES
              (1, 'Điện thoại mẫu', 1000000, 3, 8, 'SEED-PHONE', 'seed-phone', 'seed', 'VND', 0, 0, 'active', 1, 0, 0, 'TP. Hồ Chí Minh', 0),
              (2, 'Laptop mẫu', 10000000, 4, 6, 'SEED-LAPTOP', 'seed-laptop', 'seed', 'VND', 0, 0, 'active', 1, 0, 0, 'TP. Hồ Chí Minh', 0);
            INSERT INTO product_variant (product_id, sku, title, price, stock, is_active) VALUES
              (1, 'SEED-PHONE', 'Tiêu chuẩn', 1000000, 8, 1),
              (2, 'SEED-LAPTOP', 'Tiêu chuẩn', 10000000, 6, 1);
            """
        )


def make_client(tmp_path):
    shop_path = tmp_path / "shop.db"
    build_shop(shop_path)
    agent_path = tmp_path / "agent.db"
    upload_dir = tmp_path / "uploads"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{agent_path}",
        shop_database_path=shop_path,
        shop_product_upload_dir=upload_dir,
        seller_shop_slug="utech-official",
    )
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(settings)
    return TestClient(app), shop_path, upload_dir


def test_image_chat_collects_missing_fields_then_publishes_to_store(tmp_path):
    client, shop_path, upload_dir = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CopyProvider()
        uploaded = client.post(
            "/api/v1/product-drafts",
            files={"image": ("keyboard.jpg", b"\xff\xd8\xff" + b"photo", "image/jpeg")},
        )
        assert uploaded.status_code == 201
        data = uploaded.json()["data"]
        conversation_id = data["conversation_id"]
        draft = data["product_draft"]
        assert draft["missing_fields"][0] == "name"
        assert len(list(upload_dir.iterdir())) == 1

        def reply(message):
            response = client.post("/api/v1/chat", json={
                "message": message, "conversation_id": conversation_id,
            })
            assert response.status_code == 200
            return response.json()["data"]

        assert reply("Bàn phím cơ ShipCode K87")["product_draft"]["missing_fields"][0] == "price_vnd"
        assert reply("890.000đ")["product_draft"]["missing_fields"][0] == "stock"
        after_stock = reply("25 sản phẩm")["product_draft"]
        assert after_stock["category_name"] == "Máy Tính & Laptop"
        assert after_stock["status"] == "ready"
        ready = reply("AI tự viết đi")["product_draft"]
        assert ready["status"] == "ready"
        assert ready["sku"].startswith("SP-")
        assert ready["description"] != "AI tự viết đi"

        published = reply("đăng sản phẩm")
        assert published["tool"] == "publish_product"
        result = published["product_draft"]
        assert result["status"] == "published"
        assert result["published_product_id"] is not None

        # Publishing is idempotent and both catalogue and sellable variant are synchronized.
        assert client.post(f"/api/v1/product-drafts/{ready['id']}/publish").status_code == 200
        with sqlite3.connect(shop_path) as connection:
            product = connection.execute(
                "SELECT name, price, stock, status, image_url, shop_id FROM product WHERE id=?",
                (result["published_product_id"],),
            ).fetchone()
            variant = connection.execute(
                "SELECT price, stock, is_active FROM product_variant WHERE product_id=?",
                (result["published_product_id"],),
            ).fetchone()
            assert (product[0], product[1], product[2], product[3], product[5]) == (
                "Bàn phím cơ ShipCode K87", 890000.0, 25, "active", 1,
            )
            assert product[4].startswith("/static/uploads/sellerpilot/")
            assert variant == (890000.0, 25, 1)
            assert connection.execute(
                "SELECT COUNT(*) FROM product WHERE source_id=?", (f"sellerpilot-draft:{ready['id']}",)
            ).fetchone()[0] == 1


def test_invalid_image_and_cancelled_draft_cleanup(tmp_path):
    client, _shop_path, upload_dir = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        invalid = client.post(
            "/api/v1/product-drafts",
            files={"image": ("fake.jpg", b"not an image", "image/jpeg")},
        )
        assert invalid.status_code == 422

        uploaded = client.post(
            "/api/v1/product-drafts",
            files={"image": ("phone.png", b"\x89PNG\r\n\x1a\n" + b"photo", "image/png")},
        ).json()["data"]
        draft = uploaded["product_draft"]
        file_path = next(upload_dir.iterdir())
        assert file_path.exists()
        cancelled = client.post(f"/api/v1/product-drafts/{draft['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["data"]["status"] == "cancelled"
        assert not file_path.exists()


def test_generic_publish_instruction_is_not_used_as_name_or_description(tmp_path):
    client, _shop_path, _upload_dir = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CopyProvider()
        uploaded = client.post(
            "/api/v1/product-drafts",
            files={"image": ("shirt.jpg", b"\xff\xd8\xff" + b"photo", "image/jpeg")},
        ).json()["data"]
        conversation_id = uploaded["conversation_id"]

        def reply(message):
            response = client.post("/api/v1/chat", json={
                "message": message, "conversation_id": conversation_id,
            })
            assert response.status_code == 200
            return response.json()["data"]

        generic = reply("đăng sản phẩm này lên sàn giúp mình")
        assert generic["product_draft"]["name"] is None
        assert generic["product_draft"]["missing_fields"][0] == "name"
        assert "sản phẩm gì" in generic["answer"]

        named = reply("Áo thun nam cotton form rộng")
        assert named["product_draft"]["name"] == "Áo thun nam cotton form rộng"
        assert named["product_draft"]["category_name"] == "Thời Trang Nam"
        assert named["product_draft"]["missing_fields"][0] == "price_vnd"

        reply("249.000đ")
        reply("30")
        ready = reply("AI tự viết đi")
        assert ready["product_draft"]["status"] == "ready"
        assert ready["product_draft"]["description"] != "AI tự viết đi"


def test_labeled_product_details_are_parsed_as_data_in_one_message(tmp_path):
    client, _shop_path, _upload_dir = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CopyProvider()
        uploaded = client.post(
            "/api/v1/product-drafts",
            files={"image": ("appliance.webp", b"RIFF0000WEBP" + b"photo", "image/webp")},
        ).json()["data"]

        response = client.post("/api/v1/chat", json={
            "conversation_id": uploaded["conversation_id"],
            "message": (
                "Tên sản phẩm: Nồi chiên không dầu AirPro, giá bán: 1.290.000đ, "
                "tồn kho: 14, ngành hàng: Nhà Cửa & Đời Sống, mô tả: AI tự viết"
            ),
        })
        assert response.status_code == 200
        draft = response.json()["data"]["product_draft"]
        assert draft["status"] == "ready"
        assert draft["name"] == "Nồi chiên không dầu AirPro"
        assert draft["price_vnd"] == 1_290_000
        assert draft["stock"] == 14
        assert draft["category_name"] == "Nhà Cửa & Đời Sống"
        assert draft["description"] != "AI tự viết"


def test_natural_per_item_price_and_approximate_fruit_stock_are_not_asked_again(tmp_path):
    class PepperProvider(CopyProvider):
        async def respond(self, message, *, history, facts):
            assert facts['price_vnd'] == 15_000
            assert facts['stock'] == 10
            return json.dumps({
                'name': 'Ớt cầu vồng',
                'description': 'Ớt cầu vồng nhiều màu, bán theo từng trái dựa trên hình ảnh sản phẩm.',
                'category_id': 7,
                'clarification': None,
            }, ensure_ascii=False)

    client, _shop_path, _upload_dir = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = PepperProvider()
        uploaded = client.post(
            '/api/v1/product-drafts',
            files={'image': ('pepper.jpg', b'\xff\xd8\xffphoto', 'image/jpeg')},
        ).json()['data']
        response = client.post('/api/v1/chat', json={
            'conversation_id': uploaded['conversation_id'],
            'message': (
                'Đây là ớt cầu vồng, bạn hãy dựa vào hình và mô tả sản phẩm; '
                'giá của nó là 15k/trái và còn khoảng 10 trái.'
            ),
        })
        assert response.status_code == 200
        data = response.json()['data']
        draft = data['product_draft']
        assert draft['price_vnd'] == 15_000
        assert draft['stock'] == 10
        assert draft['status'] == 'ready'
        assert 'giá bán' not in data['answer'].lower()


def test_multiple_images_are_preserved_in_draft_and_marketplace_gallery(tmp_path):
    client, shop_path, upload_dir = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        images = [
            b"\xff\xd8\xff" + b"front",
            b"\x89PNG\r\n\x1a\n" + b"side",
            b"RIFF0000WEBP" + b"detail",
        ]
        uploaded = client.post("/api/v1/product-drafts/images-data", json={
            "images_base64": [base64.b64encode(image).decode("ascii") for image in images],
        })
        assert uploaded.status_code == 201
        data = uploaded.json()["data"]
        draft = data["product_draft"]
        assert draft["image_count"] == 3
        assert len(draft["preview_urls"]) == 3
        assert len(list(upload_dir.iterdir())) == 3
        for preview_url in draft["preview_urls"]:
            assert client.get("/api/v1" + preview_url).status_code == 200

        completed = client.post("/api/v1/chat", json={
            "conversation_id": data["conversation_id"],
            "message": (
                "Tên sản phẩm: Bộ nồi inox gia đình, giá bán: 799.000đ, tồn kho: 18, "
                "ngành hàng: Nhà Cửa & Đời Sống, mô tả: Bộ nồi inox dùng trong gian bếp gia đình."
            ),
        }).json()["data"]["product_draft"]
        assert completed["status"] == "ready"
        published = client.post(f"/api/v1/product-drafts/{completed['id']}/publish")
        assert published.status_code == 200
        with sqlite3.connect(shop_path) as connection:
            row = connection.execute(
                "SELECT image_url, extra_images FROM product WHERE id=?",
                (published.json()["data"]["published_product_id"],),
            ).fetchone()
        assert row[0].startswith("/static/uploads/sellerpilot/")
        assert len(json.loads(row[1])) == 2


def test_all_marketplace_categories_are_available_even_without_shop_products(tmp_path):
    client, _shop_path, _upload_dir = make_client(tmp_path)
    with client:
        categories = client.app.state.shop_repository.product_categories()
        assert [item["name"] for item in categories] == [
            "Thời Trang Nam", "Điện Thoại & Phụ Kiện",
            "Máy Tính & Laptop", "Nhà Cửa & Đời Sống",
        ]


def test_image_data_upload_supports_native_clients_without_multipart(tmp_path):
    client, _shop_path, upload_dir = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        image = b"\xff\xd8\xff" + b"native-photo"
        uploaded = client.post("/api/v1/product-drafts/image-data", json={
            "image_base64": base64.b64encode(image).decode("ascii"),
            "conversation_id": None,
        })
        assert uploaded.status_code == 201
        data = uploaded.json()["data"]
        assert data["answer"] == "Mình đã nhận ảnh. **Sản phẩm này tên gì?**"
        assert data["product_draft"]["missing_fields"][0] == "name"
        assert len(list(upload_dir.iterdir())) == 1

        invalid = client.post("/api/v1/product-drafts/image-data", json={
            "image_base64": "khong-phai-base64***",
        })
        assert invalid.status_code == 422


def upload_and_reply(client):
    data = client.post('/api/v1/product-drafts', files={
        'image': ('product.jpg', b'\xff\xd8\xffphoto', 'image/jpeg'),
    }).json()['data']

    def reply(message):
        response = client.post('/api/v1/chat', json={
            'message': message, 'conversation_id': data['conversation_id'],
        })
        assert response.status_code == 200, response.text
        return response.json()['data']
    return data, reply


@pytest.mark.parametrize('message', [
    'đăng sản phẩm này lên cho tôi được không',
    'đăng sản phẩm này lên giúp tôi',
    'vui lòng đăng sản phẩm này lên shop cho em nha',
    'AI tự viết tiêu đề và nội dung giúp tôi',
    'viết caption giúp tôi',
])
def test_requests_never_become_catalogue_content_or_pet_category(tmp_path, message):
    client, shop_path, _ = make_client(tmp_path)
    with sqlite3.connect(shop_path) as conn:
        conn.execute("INSERT INTO category VALUES (9, 'Chăm Sóc Thú Cưng', 5)")
    with client:
        client.app.state.ai_provider = CopyProvider()
        _, reply = upload_and_reply(client)
        result = reply(message)
        draft = result['product_draft']
        assert draft['name'] is None
        assert draft['description'] is None
        assert draft['category_id'] is None
        assert draft['status'] == 'collecting'
        assert result['provider'] == 'ollama'
        assert result['model'] == 'test-copy-model'


def test_auto_copy_request_survives_clarifications_and_rewrites_ready_draft(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        provider = CopyProvider()
        client.app.state.ai_provider = provider
        _, reply = upload_and_reply(client)
        reply('AI tự viết caption ngắn, giọng tự nhiên giúp tôi')
        reply('Bàn phím cơ Nova K75')
        reply('990k')
        ready = reply('20')['product_draft']
        assert ready['status'] == 'ready'
        assert 'Nova K75' in ready['description']
        assert 'caption ngắn' in provider.calls[-1]['facts']['copy_instructions']
        count = len(provider.calls)
        rewritten = reply('Viết lại tiêu đề và nội dung chuyên nghiệp hơn')
        assert len(provider.calls) == count + 1
        assert rewritten['product_draft']['status'] == 'ready'
        assert rewritten['provider'] == 'ollama'


def test_offline_copy_does_not_silently_create_template_and_claim_ready(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        _, reply = upload_and_reply(client)
        reply('Bàn phím Nova K75')
        reply('990k')
        failed = reply('20')
        draft = failed['product_draft']
        assert draft['status'] == 'collecting'
        assert draft['description'] is None
        assert draft['price_vnd'] == 990000 and draft['stock'] == 20
        assert failed['fallback_reason'] == 'provider_unavailable'
        assert 'chưa gọi được AI' in failed['answer']
        assert client.post(f"/api/v1/product-drafts/{draft['id']}/publish").status_code == 409
        client.app.state.ai_provider = CopyProvider()
        assert reply('viết lại nội dung')['product_draft']['status'] == 'ready'


def test_vision_can_identify_item_from_uploaded_image(tmp_path):
    class VisionProvider(CopyProvider):
        provider = 'opencode'
        model = 'glm-5.3-flash-free'

        async def compose_listing(self, *, facts, history, images):
            assert len(images) == 1
            assert images[0]['mime'] == 'image/jpeg'
            assert images[0]['url'].startswith('data:image/jpeg;base64,')
            assert 'đăng sản phẩm' in history[-1]['content']
            return json.dumps({'name': 'Bàn phím đen trong ảnh',
                               'description': 'Bàn phím màu đen được giới thiệu qua ảnh sản phẩm tại gian hàng.',
                               'category_id': 4, 'clarification': None})

    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = VisionProvider()
        _, reply = upload_and_reply(client)
        result = reply('đăng sản phẩm này lên cho tôi được không')
        assert result['product_draft']['name'] == 'Bàn phím đen trong ảnh'
        assert result['product_draft']['category_id'] == 4
        assert result['product_draft']['missing_fields'] == ['price_vnd', 'stock']


def test_unrelated_images_require_clarification_even_with_price_and_stock(tmp_path):
    class AmbiguousProvider(CopyProvider):
        async def compose_listing(self, *, facts, history, images):
            assert len(images) == 2
            return json.dumps({'clarification': 'Ảnh có bàn phím và hộp PS Vita, bạn muốn bán món nào?'})

    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = AmbiguousProvider()
        uploaded = client.post('/api/v1/product-drafts/images-data', json={
            'images_base64': [base64.b64encode(b'\xff\xd8\xffphoto').decode()] * 2,
        }).json()['data']
        response = client.post('/api/v1/chat', json={
            'conversation_id': uploaded['conversation_id'],
            'message': 'đăng sản phẩm này lên cho tôi, giá: 1.000.000đ, tồn kho: 20, AI tự viết nội dung',
        }).json()['data']
        draft = response['product_draft']
        assert draft['name'] is None and draft['description'] is None
        assert draft['status'] == 'collecting'
        assert draft['price_vnd'] == 1000000 and draft['stock'] == 20
        assert 'bạn muốn bán món nào' in response['answer']
        assert response['fallback_reason'] is None


def test_old_command_named_draft_is_blocked_at_publish_and_repaired_in_chat(tmp_path):
    from app.models.product_draft import ProductDraft
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CopyProvider()
        uploaded, reply = upload_and_reply(client)
        draft_id = uploaded['product_draft']['id']
        with client.app.state.session_factory() as session:
            draft = session.get(ProductDraft, draft_id)
            draft.name = 'đăng sản phẩm này lên cho tôi được không'
            draft.description = 'AI tự viết đi'
            draft.price_vnd, draft.stock, draft.category_id = 1000000, 20, 3
            draft.category_name, draft.status = 'Chăm Sóc Thú Cưng', 'ready'
            session.commit()
        blocked = client.post(f'/api/v1/product-drafts/{draft_id}/publish')
        assert blocked.status_code == 409
        repaired = reply('viết lại nội dung')['product_draft']
        assert repaired['name'] is None and repaired['category_id'] is None
        assert repaired['stock'] == 20 and repaired['price_vnd'] == 1000000


@pytest.mark.parametrize('model_copy', [
    'Đây là mô tả nhưng không phải JSON',
    json.dumps({'name': 'đăng sản phẩm này lên cho tôi', 'description': 'Nội dung mô tả sản phẩm',
                'category_id': 4, 'clarification': None}),
    json.dumps({'name': 'Bàn phím Nova', 'description': 'Nội dung mô tả sản phẩm',
                'category_id': 9999, 'clarification': None}),
])
def test_invalid_model_copy_never_becomes_ready(tmp_path, model_copy):
    class InvalidProvider(CopyProvider):
        async def respond(self, *_args, **_kwargs):
            return model_copy
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = InvalidProvider()
        _, reply = upload_and_reply(client)
        draft = reply('Tên: Bàn phím Nova, giá: 990k, tồn kho: 20, mô tả: AI tự viết')
        assert draft['product_draft']['status'] == 'collecting'
        assert draft['product_draft']['description'] is None
        assert draft['fallback_reason'] == 'invalid_response'


def test_shop_question_can_interrupt_and_resume_a_draft_without_changing_its_name(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        uploaded, reply = upload_and_reply(client)
        named = reply('Bàn phím Nova K75')['product_draft']
        assert named['price_vnd'] is None
        summary = reply('Doanh thu hôm nay bao nhiêu?')
        assert summary['tool'] == 'get_shop_summary'
        assert summary['product_draft'] is None
        resumed = reply('990k')['product_draft']
        assert resumed['name'] == 'Bàn phím Nova K75'
        assert resumed['price_vnd'] == 990000


def test_cost_clarification_during_draft_is_not_used_as_selling_price(tmp_path):
    class CostAdvisor(OfflineProvider):
        natural_responses = True
        provider = 'opencode'
        model = 'glm-5.3-flash-free'

        async def analyze_advice(self, message, *, history, context):
            updates = [] if message != '100k' else [{'field': 'unit_cost_vnd', 'value': 100000, 'evidence': '100k'}]
            return json.dumps({'topic': 'pricing', 'economics': updates})

        async def respond(self, message, *, history, facts):
            from app.services.advisor import pricing_reply
            return pricing_reply(facts['pricing_analysis'])

    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CostAdvisor()
        uploaded, reply = upload_and_reply(client)
        reply('Bàn phím Nova K75')
        result = reply('Nên bán giá bao nhiêu thì có lời?')
        assert result['facts']['pricing_analysis']['status'] == 'missing_cost'
        cost = reply('100k')
        assert cost['facts']['pricing_analysis']['inputs']['unit_cost_vnd'] == 100000
        from app.models.product_draft import ProductDraft
        with client.app.state.session_factory() as session:
            draft = session.get(ProductDraft, uploaded['product_draft']['id'])
            assert draft.price_vnd is None
