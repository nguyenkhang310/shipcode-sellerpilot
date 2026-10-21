from app.scripts.check_store import same_shop_database


def test_store_and_api_relative_paths_resolve_against_their_own_workdirs(tmp_path):
    backend, web = tmp_path / 'backend', tmp_path / 'UTE MALL'
    assert same_shop_database('../UTE MALL/instance/ecommerce.db', None, backend_dir=backend, store_dir=web)
    assert not same_shop_database('instance/ecommerce.db', None, backend_dir=backend, store_dir=web)
    assert same_shop_database('../data/shop.db', '../data/shop.db', backend_dir=backend, store_dir=web)


def test_distinct_ledgers_are_rejected_and_links_to_the_same_file_are_accepted(tmp_path):
    first, second = tmp_path/'first.db', tmp_path/'second.db'
    first.touch(); second.touch()
    assert not same_shop_database(first, str(second))
    link = tmp_path/'link.db'
    link.symlink_to(first)
    assert same_shop_database(first, str(link))
