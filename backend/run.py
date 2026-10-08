import os
import sys
import uuid

# Asegurar codificación UTF-8 en salida de consola Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app import create_app
from app.extensions import db
from app.models.tenant import Tenant
from app.models.user import User
from app.models.product import Category, Product
from app.middlewares.auth import hash_password

app = create_app()

def seed_demo_data():
    """Siembra datos iniciales de demostración si la base de datos está vacía."""
    with app.app_context():
        db.create_all()

        # Verificar si ya existe una tienda
        if Tenant.query.first() is None:
            print("[+] Inicializando datos semilla para demostracion...")

            # 1. Crear Tenant demo
            demo_tenant_id = str(uuid.uuid4())
            tenant = Tenant(
                id=demo_tenant_id,
                business_name="Supermercado & Tienda Demo",
                tax_id="NIT 900.123.456-7",
                phone="+57 300 123 4567",
                email="contacto@tiendademo.com",
                address="Av. Principal # 10-20, Bogotá",
                currency_symbol="$",
                status="ACTIVE"
            )
            db.session.add(tenant)

            # 2. Crear Usuarios (Admin y Cajero)
            admin_user = User(
                id=str(uuid.uuid4()),
                tenant_id=demo_tenant_id,
                full_name="Administrador Principal",
                email="admin@pos.com",
                password_hash=hash_password("admin123"),
                role="ADMIN",
                is_active=True
            )
            db.session.add(admin_user)

            cashier_user = User(
                id=str(uuid.uuid4()),
                tenant_id=demo_tenant_id,
                full_name="Cajero de Turno",
                email="cajero@pos.com",
                password_hash=hash_password("cajero123"),
                role="CASHIER",
                is_active=True
            )
            db.session.add(cashier_user)

            # 3. Crear Categorías
            cat_bebidas = Category(
                id=str(uuid.uuid4()),
                tenant_id=demo_tenant_id,
                name="Bebidas y Refrescos",
                description="Gaseosas, jugos, aguas y energizantes"
            )
            cat_snacks = Category(
                id=str(uuid.uuid4()),
                tenant_id=demo_tenant_id,
                name="Snacks y Pasabocas",
                description="Papas fritas, galletas y chocolates"
            )
            cat_lacteos = Category(
                id=str(uuid.uuid4()),
                tenant_id=demo_tenant_id,
                name="Lácteos y Derivados",
                description="Leche, quesos y yogures"
            )
            db.session.add_all([cat_bebidas, cat_snacks, cat_lacteos])

            # 4. Crear Productos
            sample_products = [
                Product(
                    id=str(uuid.uuid4()),
                    tenant_id=demo_tenant_id,
                    category=cat_bebidas,
                    barcode="770123456001",
                    name="Coca Cola Original 500ml",
                    cost_price=2200.00,
                    sale_price=3500.00,
                    stock=45,
                    min_stock=10
                ),
                Product(
                    id=str(uuid.uuid4()),
                    tenant_id=demo_tenant_id,
                    category=cat_bebidas,
                    barcode="770123456002",
                    name="Agua Mineral Cristal 600ml",
                    cost_price=1200.00,
                    sale_price=2000.00,
                    stock=30,
                    min_stock=8
                ),
                Product(
                    id=str(uuid.uuid4()),
                    tenant_id=demo_tenant_id,
                    category=cat_snacks,
                    barcode="770123456003",
                    name="Papas Margarita Limón 115g",
                    cost_price=2800.00,
                    sale_price=4200.00,
                    stock=25,
                    min_stock=5
                ),
                Product(
                    id=str(uuid.uuid4()),
                    tenant_id=demo_tenant_id,
                    category=cat_snacks,
                    barcode="770123456004",
                    name="Galletas Festival Chocolate",
                    cost_price=1500.00,
                    sale_price=2500.00,
                    stock=50,
                    min_stock=12
                ),
                Product(
                    id=str(uuid.uuid4()),
                    tenant_id=demo_tenant_id,
                    category=cat_lacteos,
                    barcode="770123456005",
                    name="Leche Entera Alquería 1L",
                    cost_price=3400.00,
                    sale_price=4800.00,
                    stock=20,
                    min_stock=6
                ),
                Product(
                    id=str(uuid.uuid4()),
                    tenant_id=demo_tenant_id,
                    category=cat_lacteos,
                    barcode="770123456006",
                    name="Queso Doble Crema Alpina 250g",
                    cost_price=6500.00,
                    sale_price=9200.00,
                    stock=14,
                    min_stock=4
                ),
            ]
            db.session.add_all(sample_products)
            db.session.commit()
            print("[OK] Datos semilla cargados exitosamente.")
            print("[KEY] Credenciales Demo:")
            print("   - Admin:  admin@pos.com  / admin123")
            print("   - Cajero: cajero@pos.com / cajero123")

if __name__ == '__main__':
    seed_demo_data()
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f"[START] SISTEMA POS PWA API escuchando en http://{host}:{port}")
    app.run(host=host, port=port, debug=True)

