"""Read-only Snowflake analytics and a portable, aggregate-only snapshot."""
import base64
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'reports' / 'snowflake' / 'warehouse_snapshot.json'
QUERIES = {
    'monthly': '''SELECT SALES_MONTH, ROUND(REVENUE, 2) AS REVENUE,
        TOTAL_ORDERS, GROWTH_PERCENT FROM V_MONTHLY_REVENUE ORDER BY SALES_MONTH''',
    'markets': '''SELECT COUNTRY, ROUND(REVENUE, 2) AS REVENUE,
        TOTAL_ORDERS, REVENUE_SHARE FROM V_COUNTRY_PERFORMANCE
        ORDER BY REVENUE DESC''',
    'products': '''SELECT STOCK_CODE, DESCRIPTION, NET_UNITS_SOLD,
        ROUND(REVENUE, 2) AS REVENUE FROM V_PRODUCT_PERFORMANCE
        ORDER BY REVENUE DESC, STOCK_CODE LIMIT 15''',
    'segments': '''SELECT CUSTOMER_SEGMENT, COUNT(*) AS CUSTOMERS,
        ROUND(SUM(MONETARY), 2) AS REVENUE FROM V_CUSTOMER_RFM
        GROUP BY CUSTOMER_SEGMENT ORDER BY CUSTOMERS DESC, CUSTOMER_SEGMENT''',
}


def json_value(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def fetch_cloud(account, encrypted_pem, passphrase):
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    private = serialization.load_pem_private_key(
        encrypted_pem, password=passphrase.encode('utf-8')
    )
    der = private.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    results = {}
    with snowflake.connector.connect(
        account=account, user='RETAILIQ_APP', private_key=der,
        authenticator='SNOWFLAKE_JWT', warehouse='RETAIL_WH',
        database='RETAILIQ_DB', schema='ANALYTICS', role='RETAILIQ_READER',
        login_timeout=30, network_timeout=60,
        session_parameters={'STATEMENT_TIMEOUT_IN_SECONDS': 60,
                            'QUERY_TAG': 'RetailIQ_Snowflake_Analytics'}
    ) as conn:
        with conn.cursor() as cursor:
            for name, sql in QUERIES.items():
                cursor.execute(sql)
                columns = [col[0].lower() for col in cursor.description]
                results[name] = [
                    dict(zip(columns, map(json_value, row)))
                    for row in cursor.fetchall()
                ]
    return {'source': 'Snowflake',
            'queried_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'tables': results}


def fetch_from_config(config):
    return fetch_cloud(str(config['account']),
                       base64.b64decode(str(config['private_key_b64']), validate=True),
                       str(config['passphrase']))


def read_snapshot():
    payload = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    if not all(name in payload['tables'] for name in QUERIES):
        raise ValueError('Incomplete snapshot')
    return payload


def main():
    account = input('Snowflake account identifier: ').strip()
    password = getpass('Enter private key passphrase: ')
    key_path = Path(os.environ['LOCALAPPDATA']) / 'RetailIQ' / 'keys' / 'snowflake_key.p8'
    payload = fetch_cloud(account, key_path.read_bytes(), password)
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print('Snowflake analytics snapshot saved:', SNAPSHOT.relative_to(ROOT))
    print('Only aggregate historical query results were exported.')


if __name__ == '__main__':
    main()
