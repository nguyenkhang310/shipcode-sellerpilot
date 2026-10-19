"""Tenant-scoped business evidence. No customer data or write operations."""
import sqlite3
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from app.integrations.management import _scope
from app.integrations.ute_mall import ShopDatabaseError


def _amount(value):
    return int(round(Decimal(str(value or 0))))


def _percent(numerator, denominator):
    return round(numerator * 100 / denominator, 2) if denominator else None


def business_snapshot(shop, days=7, *, now=None):
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 30:
        raise ValueError('Business reporting period must be 1–30 days')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Business snapshot requires timezone-aware now')
    now = now.astimezone(timezone.utc)
    local_today = now.astimezone(shop.timezone).date()
    first_day = local_today - timedelta(days=days - 1)
    start = datetime.combine(first_day, time.min, shop.timezone).astimezone(timezone.utc)
    previous_start, previous_end = start - timedelta(days=days), now - timedelta(days=days)
    stamp = lambda dt: dt.replace(tzinfo=None).isoformat(sep=' ')
    periods = {name: {'order_count': 0, 'order_value_vnd': 0, 'all_order_count': 0,
                      'cancelled_count': 0, 'returned_count': 0, 'delivered_value_vnd': 0}
               for name in ('current', 'previous')}
    series = {str(first_day + timedelta(days=i)): {'order_count': 0, 'order_value_vnd': 0}
              for i in range(days)}
    try:
        with shop._connect() as connection:
            connection.execute('BEGIN')
            order_scope, order_params = _scope(connection, shop, 'order', 'o')
            product_scope, product_params = _scope(connection, shop, 'product', 'p')
            order_periods = {}
            for row in connection.execute(
                f'SELECT o.id, o.total_amount, o.status, o.created_at FROM "order" o '
                f'WHERE {order_scope} AND o.created_at >= ? AND o.created_at <= ?',
                [*order_params, stamp(previous_start), stamp(now)],
            ):
                created = datetime.fromisoformat(row['created_at'])
                created = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created.astimezone(timezone.utc)
                period = ('current' if start <= created <= now else
                          'previous' if previous_start <= created <= previous_end else None)
                if period is None:
                    continue
                stats = periods[period]
                stats['all_order_count'] += 1
                if row['status'] in ('cancelled', 'returned'):
                    stats['cancelled_count' if row['status'] == 'cancelled' else 'returned_count'] += 1
                    continue
                order_periods[row['id']] = period
                value = _amount(row['total_amount'])
                stats['order_count'] += 1
                stats['order_value_vnd'] += value
                if row['status'] == 'delivered':
                    stats['delivered_value_vnd'] += value
                if period == 'current':
                    point = series[str(created.astimezone(shop.timezone).date())]
                    point['order_count'] += 1
                    point['order_value_vnd'] += value

            # Parent stock may mirror variant stock. Use active variants when any
            # variants exist; never add parent + variant inventory together.
            catalog = {}
            for row in connection.execute(
                f'''SELECT p.id, p.sku, p.name, p.price, p.status,
                       CASE WHEN EXISTS (SELECT 1 FROM product_variant v WHERE v.product_id=p.id)
                            THEN COALESCE((SELECT SUM(v.stock) FROM product_variant v
                                           WHERE v.product_id=p.id AND v.is_active=1), 0)
                            ELSE p.stock END AS available_stock
                    FROM product p WHERE {product_scope}''', product_params,
            ):
                catalog[row['id']] = {
                    'product_id': row['id'], 'sku': row['sku'], 'name': row['name'],
                    'price_vnd': _amount(row['price']), 'status': row['status'],
                    'available_stock': row['available_stock'],
                    'units_sold': 0, 'previous_units_sold': 0, 'item_sales_value_vnd': 0,
                    'order_count': 0,
                }
            product_orders = {}
            matched, unmatched = 0, 0
            for row in connection.execute(
                f'''SELECT i.order_id, i.product_id, i.quantity, i.price
                    FROM order_item i JOIN "order" o ON o.id=i.order_id
                    WHERE {order_scope} AND o.created_at >= ? AND o.created_at <= ?''',
                [*order_params, stamp(previous_start), stamp(now)],
            ):
                period = order_periods.get(row['order_id'])
                if period is None:
                    continue
                item = catalog.get(row['product_id'])
                if not item:
                    if period == 'current':
                        unmatched += 1
                    continue
                quantity = row['quantity']
                if quantity <= 0:
                    if period == 'current':
                        unmatched += 1
                    continue
                if period == 'previous':
                    item['previous_units_sold'] += quantity
                else:
                    matched += 1
                    item['units_sold'] += quantity
                    item['item_sales_value_vnd'] += _amount(Decimal(str(row['price'])) * quantity)
                    product_orders.setdefault(row['product_id'], set()).add(row['order_id'])
    except (sqlite3.Error, ValueError, TypeError) as error:
        raise ShopDatabaseError('Cannot read business performance') from error

    for stats in periods.values():
        stats['average_order_vnd'] = round(stats['order_value_vnd'] / stats['order_count']) if stats['order_count'] else 0
        stats['cancelled_rate_percent'] = _percent(stats['cancelled_count'], stats['all_order_count'])
        stats['returned_rate_percent'] = _percent(stats['returned_count'], stats['all_order_count'])
    current, previous = periods['current'], periods['previous']
    for item in catalog.values():
        item['order_count'] = len(product_orders.get(item['product_id'], ()))
        item['observed_units_per_calendar_day'] = round(item['units_sold'] / days, 2)
        item['stock_cover_days_estimate'] = round(item['available_stock'] * days / item['units_sold'], 1) if item['units_sold'] else None
    sold = sorted((item for item in catalog.values() if item['units_sold']),
                  key=lambda item: (-item['units_sold'], -item['item_sales_value_vnd'], item['product_id']))
    candidates = sorted((item for item in catalog.values() if item['status'] == 'active' and item['available_stock'] > 5),
                        key=lambda item: (-item['units_sold'], -item['available_stock'], item['product_id']))[:5]
    return {
        'as_of': now.isoformat(), 'timezone': shop.timezone_name,
        'period': {'days': days, 'from_date': str(first_day), 'to_date': str(local_today),
                   'through': now.isoformat(), 'includes_partial_today': True},
        'current': current, 'previous': previous,
        'comparison': {'previous_from': previous_start.isoformat(), 'previous_through': previous_end.isoformat(),
                       'basis': 'same_elapsed_duration_shifted_by_days',
                       'order_value_delta_vnd': current['order_value_vnd'] - previous['order_value_vnd'],
                       'order_value_change_percent': _percent(current['order_value_vnd'] - previous['order_value_vnd'], previous['order_value_vnd']),
                       'order_count_delta': current['order_count'] - previous['order_count']},
        'daily_sales': [{'date': day, **values} for day, values in series.items()],
        'period_top_products': sold[:5], 'promotion_candidates': candidates,
        'stock_risks': [item for item in sold if item['status'] == 'active'
                        and (item['available_stock'] <= 5 or item['stock_cover_days_estimate'] < 7)][:5],
        'active_products_without_period_sales': sum(item['status'] == 'active' and item['units_sold'] == 0 for item in catalog.values()),
        'attribution': {'matched_current_item_lines': matched, 'unmatched_current_item_lines': unmatched,
                        'available': matched > 0, 'catalog_sold_count_used': False},
        'limits': ['Item sales use purchased line prices before order-level shipping/discount allocation; not profit or collected cash.',
                   'Stock cover is a descriptive estimate using period units/calendar days including partial today, not a forecast.',
                   'No item rows means unknown product performance, not proof of zero product demand.',
                   'No TikTok views, clicks, ad spend or attributed orders are connected.'],
    }
