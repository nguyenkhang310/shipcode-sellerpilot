from pathlib import Path
import pytest
from benchmark_ai import verify_disposable_fixture
from test_product_drafts import make_client


def test_live_benchmark_fixture_is_scoped_to_its_temporary_directory(tmp_path):
    fixture, _, _ = make_client(tmp_path)
    verify_disposable_fixture(fixture.app.state.settings, tmp_path)


@pytest.mark.parametrize('field', ['shop_database_path','database_url','shop_static_dir','shop_product_upload_dir'])
def test_live_benchmark_refuses_any_external_data_path(tmp_path, field):
    fixture, _, _ = make_client(tmp_path)
    outside = tmp_path.parent / 'not-a-benchmark-fixture'
    value = 'sqlite:///'+str(outside) if field == 'database_url' else Path(outside)
    setattr(fixture.app.state.settings, field, value)
    with pytest.raises(RuntimeError): verify_disposable_fixture(fixture.app.state.settings, tmp_path)
