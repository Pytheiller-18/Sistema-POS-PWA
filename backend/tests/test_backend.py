import unittest
import uuid
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.config import Config
from app.extensions import db
from app.models.tenant import Tenant
from app.models.user import User
from app.models.product import Category, Product
from app.models.sale import Sale
from app.middlewares.auth import hash_password, generate_jwt_token

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class POSBackendTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Tenant A (Tienda Alpha)
        self.tenant_a = Tenant(
            id=str(uuid.uuid4()),
            business_name="Tienda Alpha",
            tax_id="NIT-111",
            status="ACTIVE"
        )
        db.session.add(self.tenant_a)

        self.user_a_admin = User(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_a.id,
            full_name="Admin Alpha",
            email="admin@alpha.com",
            password_hash=hash_password("pass123"),
            role="ADMIN",
            is_active=True
        )
        db.session.add(self.user_a_admin)

        # Tenant B (Tienda Beta - Aislada)
        self.tenant_b = Tenant(
            id=str(uuid.uuid4()),
            business_name="Tienda Beta",
            tax_id="NIT-222",
            status="ACTIVE"
        )
        db.session.add(self.tenant_b)

        self.user_b_admin = User(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_b.id,
            full_name="Admin Beta",
            email="admin@beta.com",
            password_hash=hash_password("pass123"),
            role="ADMIN",
            is_active=True
        )
        db.session.add(self.user_b_admin)

        # Producto de Tenant A
        self.product_a = Product(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_a.id,
            barcode="77000000001",
            name="Café Gourmet Alpha 500g",
            cost_price=10.0,
            sale_price=18.0,
            stock=100,
            min_stock=10,
            is_active=True
        )
        db.session.add(self.product_a)

        # Producto de Tenant B
        self.product_b = Product(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_b.id,
            barcode="77000000002",
            name="Té Especial Beta",
            cost_price=5.0,
            sale_price=8.0,
            stock=50,
            min_stock=5,
            is_active=True
        )
        db.session.add(self.product_b)

        db.session.commit()

        # Generar tokens
        self.token_a = generate_jwt_token(self.user_a_admin.id, self.tenant_a.id, "ADMIN", self.tenant_a.business_name)
        self.token_b = generate_jwt_token(self.user_b_admin.id, self.tenant_b.id, "ADMIN", self.tenant_b.business_name)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_health_check(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json['multi_tenant'])

    def test_multi_tenant_catalog_isolation(self):
        """Doble Verificación: Tenant A no puede ver productos de Tenant B."""
        headers_a = {'Authorization': f'Bearer {self.token_a}'}
        res_a = self.client.get('/api/v1/products', headers=headers_a)
        self.assertEqual(res_a.status_code, 200)
        products_a = res_a.json['products']
        self.assertEqual(len(products_a), 1)
        self.assertEqual(products_a[0]['name'], "Café Gourmet Alpha 500g")

        # Intentar acceder directamente con ID de Tenant B usando token de Tenant A
        res_cross = self.client.get(f'/api/v1/products/{self.product_b.id}', headers=headers_a)
        self.assertEqual(res_cross.status_code, 404, "Vulnerabilidad IDOR evitada: Tenant A no puede leer producto de B")

    def test_sale_processing_and_stock_deduction(self):
        """Doble Verificación: Registrar venta disminuye stock y calcula contabilidad."""
        headers_a = {'Authorization': f'Bearer {self.token_a}'}
        sale_payload = {
            'client_sync_id': str(uuid.uuid4()),
            'payment_method': 'CASH',
            'amount_paid': 50.0,
            'items': [
                {'product_id': self.product_a.id, 'quantity': 3}
            ]
        }
        res = self.client.post('/api/v1/sales', json=sale_payload, headers=headers_a)
        self.assertEqual(res.status_code, 201)
        data = res.json
        self.assertTrue(data['success'])
        self.assertEqual(data['sale']['total'], 54.0) # 18.0 * 3
        self.assertEqual(data['sale']['amount_paid'], 50.0)

        # Verificar stock actualizado
        prod = db.session.get(Product, self.product_a.id)
        self.assertEqual(prod.stock, 97, "El stock debe decrementar exactamente 3 unidades")

    def test_offline_idempotency_duplicate_prevention(self):
        """Doble Verificación: Reenviar la misma venta offline no duplica venta ni decrementa stock dos veces."""
        headers_a = {'Authorization': f'Bearer {self.token_a}'}
        fixed_sync_id = "offline-client-uuid-999"
        sale_payload = {
            'client_sync_id': fixed_sync_id,
            'items': [{'product_id': self.product_a.id, 'quantity': 2}]
        }

        # Primer envío
        res1 = self.client.post('/api/v1/sales', json=sale_payload, headers=headers_a)
        self.assertEqual(res1.status_code, 201)
        self.assertFalse(res1.json['already_synced'])

        # Segundo envío (simulando reintento por pérdida de red)
        res2 = self.client.post('/api/v1/sales', json=sale_payload, headers=headers_a)
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.json['already_synced'])

        # Verificar que solo hay 1 venta en base de datos
        sales_count = Sale.query.filter_by(tenant_id=self.tenant_a.id).count()
        self.assertEqual(sales_count, 1)

        # Stock solo se decrementó 2 unidades, no 4
        prod = db.session.get(Product, self.product_a.id)
        self.assertEqual(prod.stock, 98)

    def test_sync_sales_batch(self):
        """Doble Verificación: Procesamiento de lote offline."""
        headers_a = {'Authorization': f'Bearer {self.token_a}'}
        batch_payload = {
            'device_id': 'POS-MOBILE-01',
            'sales': [
                {
                    'client_sync_id': 'sync-batch-1',
                    'items': [{'product_id': self.product_a.id, 'quantity': 1}]
                },
                {
                    'client_sync_id': 'sync-batch-2',
                    'items': [{'product_id': self.product_a.id, 'quantity': 2}]
                }
            ]
        }
        res = self.client.post('/api/v1/sync/sales-batch', json=batch_payload, headers=headers_a)
        self.assertEqual(res.status_code, 200)
        summary = res.json['summary']
        self.assertEqual(summary['synced_count'], 2)
        self.assertEqual(summary['failed_count'], 0)

    def test_analytics_and_profit_reports(self):
        """Doble Verificación: Cálculos de ventas de hoy, mensuales y utilidades."""
        headers_a = {'Authorization': f'Bearer {self.token_a}'}
        
        # Registrar una venta de 4 unidades: Precio 18 c/u (Total 72), Costo 10 c/u (Costo Total 40), Ganancia 32
        sale_payload = {
            'client_sync_id': str(uuid.uuid4()),
            'items': [{'product_id': self.product_a.id, 'quantity': 4}]
        }
        self.client.post('/api/v1/sales', json=sale_payload, headers=headers_a)

        # Reporte de hoy
        res_today = self.client.get('/api/v1/reports/today', headers=headers_a)
        self.assertEqual(res_today.status_code, 200)
        self.assertEqual(res_today.json['data']['total_sales'], 72.0)
        self.assertEqual(res_today.json['data']['transaction_count'], 1)

        # Reporte de utilidades
        res_profit = self.client.get('/api/v1/reports/profit', headers=headers_a)
        self.assertEqual(res_profit.status_code, 200)
        profit_data = res_profit.json['data']
        self.assertEqual(profit_data['total_revenue'], 72.0)
        self.assertEqual(profit_data['total_cost'], 40.0)
        self.assertEqual(profit_data['gross_profit'], 32.0)
        self.assertEqual(profit_data['margin_percentage'], 44.4)

if __name__ == '__main__':
    unittest.main()
